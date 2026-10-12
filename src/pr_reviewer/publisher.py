"""Turn findings into CodeCommit comment bodies, without repeating ourselves."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field

from pr_reviewer.file_filter import SkippedFile
from pr_reviewer.findings import SEVERITIES, Finding, severity_rank
from pr_reviewer.standards import Standards

MAX_COMMENT_CHARS = 10_000  # CodeCommit rejects comments over 10,240 characters
_FP_RE = re.compile(r"pr-reviewer · fp:([0-9a-f]{12})\s*\Z")  # only our own footer counts


def footer(fingerprint: str) -> str:
    return f"pr-reviewer · fp:{fingerprint}"


def existing_fingerprints(bodies: list[str]) -> set[str]:
    return {m.group(1) for body in bodies if (m := _FP_RE.search(body))}


def commit_fingerprint(kind: str, source_commit: str) -> str:
    return hashlib.sha256(f"{kind}|{source_commit}".encode()).hexdigest()[:12]


def _finish(body: str, fingerprint: str) -> str:
    tail = f"\n\n---\n{footer(fingerprint)}"
    room = MAX_COMMENT_CHARS - len(tail)
    if len(body) > room:
        marker = "\n\n[comment truncated]"
        body = body[: room - len(marker)] + marker
    return body + tail


@dataclass(frozen=True)
class PublishPlan:
    inline: list[Finding]
    summary_only: list[Finding]
    overflow: list[Finding]
    previously_reported: int
    repeats: list[Finding] = field(default_factory=list)  # same issue at other lines of a file


def plan_publication(
    findings: list[Finding], already_posted: set[str], max_inline: int, inline_severities: frozenset[str]
) -> PublishPlan:
    ordered = sorted(findings, key=lambda f: (severity_rank(f.severity), f.file, f.line))
    seen: set[str] = set()
    fresh: list[Finding] = []
    repeats: list[Finding] = []
    previously_reported = 0
    for f in ordered:
        if f.fingerprint in seen:
            repeats.append(f)
            continue
        seen.add(f.fingerprint)
        if f.fingerprint in already_posted:
            previously_reported += 1
        else:
            fresh.append(f)
    candidates = [f for f in fresh if f.severity in inline_severities]
    return PublishPlan(
        inline=candidates[:max_inline],
        summary_only=[f for f in fresh if f.severity not in inline_severities],
        overflow=candidates[max_inline:],
        previously_reported=previously_reported,
        repeats=repeats,
    )


def render_inline(f: Finding) -> str:
    parts = [f"**[{f.severity.upper()} · {f.category}] {f.title}**", "", f.explanation]
    if f.suggestion:
        parts += ["", f"**Suggestion:** {f.suggestion}"]
    if f.standard_ref:
        parts += ["", f"Rule: {f.standard_ref}"]
    return _finish("\n".join(parts), f.fingerprint)


@dataclass(frozen=True)
class ReviewReport:
    source_commit: str
    reviewed_files: list[str]
    skipped: list[SkippedFile]
    partial: bool
    standards: Standards
    plan: PublishPlan


def _line(f: Finding) -> str:
    return f"- `{f.file}:{f.line}` {f.title} ({f.severity} · {f.category})"


def render_summary(report: ReviewReport) -> str:
    plan = report.plan
    new = plan.inline + plan.overflow + plan.summary_only
    lines = [f"## Automated review of `{report.source_commit[:12]}`", ""]
    if report.partial:
        lines += ["> **Partial review:** the time limit was reached; some files were not reviewed (listed below).", ""]
    if report.reviewed_files:
        counts = Counter(f.severity for f in new)
        lines.append(f"Reviewed {len(report.reviewed_files)} file(s). New issues: {len(new)} "
                     f"({', '.join(f'{s}: {counts[s]}' for s in SEVERITIES)}).")
    elif report.partial:
        lines.append("No files were reviewed before the time limit.")
    else:
        lines.append("No reviewable files in this pull request.")
    if plan.previously_reported:
        lines.append(f"{plan.previously_reported} issue(s) already reported earlier were not repeated.")
    if plan.overflow:
        lines += ["", "### More issues (not posted inline)", *map(_line, plan.overflow)]
    if plan.repeats:
        lines += ["", "### Same issue at other lines", *map(_line, plan.repeats)]
    if plan.summary_only:
        lines += ["", "### Low-severity notes", *map(_line, plan.summary_only)]
    if report.skipped:
        lines += ["", "### Not reviewed", *(f"- {s.path}: {s.reason}" for s in report.skipped)]
    lines += ["", f"Standards: {report.standards.source} (version {report.standards.version})"]
    return _finish("\n".join(lines), commit_fingerprint("summary", report.source_commit))


def render_failure(source_commit: str, request_id: str) -> str:
    body = (
        f"Automated review of `{source_commit[:12]}` could not complete. "
        f"Operators can find details in CloudWatch Logs (request id `{request_id}`)."
    )
    return _finish(body, commit_fingerprint("failure", source_commit))
