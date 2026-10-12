"""Orchestrates one review: changes -> standards -> Claude -> validated comments."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping

from pr_reviewer.diffing import build_file_diff
from pr_reviewer.file_filter import SkippedFile, content_skip_reason, language_for, select_files
from pr_reviewer.findings import validate_findings
from pr_reviewer.log import log
from pr_reviewer.publisher import (
    ReviewReport,
    commit_fingerprint,
    existing_fingerprints,
    plan_publication,
    render_failure,
    render_inline,
    render_summary,
)
from pr_reviewer.reviewer import ReviewFile, ReviewTimeBudgetExceeded, build_batches
from pr_reviewer.standards import Standards

_DEFAULT_INLINE = frozenset({"critical", "high", "medium"})
PUBLISH_RESERVE_S = 30  # Lambda time kept back for posting comments
_ALREADY_POSTED_CODES = {"IdempotencyParameterMismatchException", "IdempotentParameterMismatchException"}


def _csv(value: str) -> frozenset[str]:
    return frozenset(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True)
class Config:
    model_id: str
    standards_url: str
    repository_names: frozenset[str] = frozenset()
    max_files: int = 30
    max_inline_comments: int = 15
    max_file_bytes: int = 100_000
    inline_severities: frozenset[str] = _DEFAULT_INLINE
    effort: str = "high"
    min_remaining_ms: int = 90_000

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Config":
        return cls(
            model_id=env["MODEL_ID"],
            standards_url=env["STANDARDS_URL"],
            repository_names=_csv(env.get("REPOSITORY_NAMES", "")),
            max_files=int(env.get("MAX_FILES", "30")),
            max_inline_comments=int(env.get("MAX_INLINE_COMMENTS", "15")),
            max_file_bytes=int(env.get("MAX_FILE_BYTES", "100000")),
            inline_severities=_csv(env.get("INLINE_SEVERITIES", "")) or _DEFAULT_INLINE,
            effort=env.get("EFFORT", "high"),
        )


@dataclass(frozen=True)
class ReviewRequest:
    repository: str
    pull_request_id: str
    event: str


def run_review(
    request: ReviewRequest,
    *,
    gateway,
    reviewer,
    load_standards_fn: Callable[[str], Standards],
    config: Config,
    remaining_ms: Callable[[], int],
    request_id: str,
) -> str:
    pr = gateway.get_pull_request(request.pull_request_id)
    if pr.status != "OPEN":
        log("skipping review", pullRequestId=pr.pull_request_id, status=pr.status)
        return f"skipped: pull request is {pr.status}"
    try:
        return _review(pr, gateway, reviewer, load_standards_fn, config, remaining_ms)
    except Exception as exc:
        log("review failed", pullRequestId=pr.pull_request_id, sourceCommit=pr.source_commit, error=repr(exc))
        _post_failure_once(gateway, pr, request_id)
        raise


def _review(pr, gateway, reviewer, load_standards_fn, config: Config, remaining_ms) -> str:
    changed = gateway.get_differences(pr.repository, pr.merge_base, pr.source_commit)
    selected, skipped = select_files(changed, config.max_files)

    files: list[ReviewFile] = []
    for cf in selected:
        after_bytes = gateway.get_blob(pr.repository, cf.after_blob_id)
        reason = content_skip_reason(after_bytes, config.max_file_bytes)
        if reason:
            skipped.append(SkippedFile(cf.path, reason))
            continue
        before = (
            gateway.get_blob(pr.repository, cf.before_blob_id).decode("utf-8", errors="replace")
            if cf.before_blob_id else ""
        )
        after = after_bytes.decode("utf-8")
        diff = build_file_diff(cf.path, before, after)
        if not diff.changed_lines:
            skipped.append(SkippedFile(cf.path, "no added or modified lines"))
            continue
        files.append(ReviewFile(cf.path, language_for(cf.path), diff, after))

    standards = load_standards_fn(config.standards_url)
    findings = []
    reviewed: list[str] = []
    partial = False
    batches = build_batches(files) if files else []
    for index, batch in enumerate(batches):
        if remaining_ms() < config.min_remaining_ms:
            partial = True
            skipped += [SkippedFile(f.path, "not reviewed: time limit reached") for b in batches[index:] for f in b]
            break
        paths = [f.path for f in batch]
        try:
            raw = reviewer.review_batch(standards, batch,
                                        time_budget_s=remaining_ms() / 1000 - PUBLISH_RESERVE_S)
        except ReviewTimeBudgetExceeded:
            partial = True
            skipped += [SkippedFile(f.path, "not reviewed: time limit reached") for b in batches[index:] for f in b]
            break
        except Exception as exc:
            log("batch review failed", files=paths, error=repr(exc))
            skipped += [SkippedFile(p, f"review failed ({type(exc).__name__})") for p in paths]
            continue
        kept, dropped = validate_findings(raw, {f.path: f.diff.changed_lines for f in batch})
        if dropped:
            log("dropped findings outside changed lines", count=len(dropped))
        findings += kept
        reviewed += paths

    if files and not reviewed and not partial:
        # Systemic failure (permissions, wrong model, outage): fail loudly, not "nothing to review".
        raise RuntimeError("every review batch failed")

    posted = existing_fingerprints(gateway.list_comment_bodies(pr.pull_request_id))
    plan = plan_publication(findings, posted, config.max_inline_comments, config.inline_severities)
    published, unpostable = [], []
    for f in plan.inline:
        try:
            gateway.post_comment(pr, render_inline(f), f"{f.fingerprint}-{pr.source_commit[:12]}",
                                 file_path=f.file, line=f.line)
            published.append(f)
        except Exception as exc:
            if _error_code(exc) in _ALREADY_POSTED_CODES:
                continue  # a concurrent or earlier run already posted this finding
            log("inline comment failed", file=f.file, line=f.line, error=repr(exc))
            unpostable.append(f)
    plan = replace(plan, inline=published, overflow=unpostable + plan.overflow)

    summary_fp = commit_fingerprint("summary", pr.source_commit)
    if summary_fp not in posted:
        report = ReviewReport(pr.source_commit, reviewed, skipped, partial, standards, plan)
        gateway.post_comment(pr, render_summary(report), f"{summary_fp}-{pr.source_commit[:12]}")

    log("review complete", pullRequestId=pr.pull_request_id, sourceCommit=pr.source_commit,
        reviewed=len(reviewed), skipped=len(skipped), inline=len(plan.inline), partial=partial)
    return f"reviewed: {len(plan.inline)} inline comment(s)"


def _error_code(exc: Exception) -> str | None:
    return (getattr(exc, "response", None) or {}).get("Error", {}).get("Code")


def _post_failure_once(gateway, pr, request_id: str) -> None:
    fingerprint = commit_fingerprint("failure", pr.source_commit)
    try:
        if fingerprint in existing_fingerprints(gateway.list_comment_bodies(pr.pull_request_id)):
            return
        gateway.post_comment(pr, render_failure(pr.source_commit, request_id),
                             f"{fingerprint}-{request_id}")
    except Exception as exc:  # never mask the original failure
        log("could not post failure comment", error=repr(exc))
