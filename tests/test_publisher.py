from pr_reviewer.file_filter import SkippedFile
from pr_reviewer.findings import Finding
from pr_reviewer.publisher import (
    MAX_COMMENT_CHARS,
    PublishPlan,
    ReviewReport,
    commit_fingerprint,
    existing_fingerprints,
    footer,
    plan_publication,
    render_failure,
    render_inline,
    render_summary,
)
from pr_reviewer.standards import Standards

INLINE = frozenset({"critical", "high", "medium"})
STD = Standards("rules", "https://example/std.md", "abc123def456")


def f(title, severity="high", file="a.py", line=1, ref=None, category="bug"):
    return Finding(file, line, severity, category, title, "because", "fix it", ref)


def test_footer_round_trips_through_existing_fingerprints():
    body = "text\n\n---\n" + footer("0123456789ab")
    assert existing_fingerprints([body, "unrelated"]) == {"0123456789ab"}


def test_commit_fingerprint_is_stable_and_kind_specific():
    assert commit_fingerprint("summary", "abc") == commit_fingerprint("summary", "abc")
    assert commit_fingerprint("summary", "abc") != commit_fingerprint("failure", "abc")
    assert len(commit_fingerprint("summary", "abc")) == 12


def test_plan_routes_by_severity_dedupes_and_caps():
    findings = [
        f("low one", severity="low"),
        f("medium one", severity="medium"),
        f("critical one", severity="critical"),
        f("high one", severity="high"),
        f("high one", severity="high", line=9),  # same fingerprint -> in-run duplicate
        f("already posted", severity="high"),
    ]
    posted = {f("already posted").fingerprint}
    plan = plan_publication(findings, posted, max_inline=2, inline_severities=INLINE)
    assert [x.title for x in plan.inline] == ["critical one", "high one"]
    assert [x.title for x in plan.overflow] == ["medium one"]
    assert [x.title for x in plan.summary_only] == ["low one"]
    assert plan.previously_reported == 1


def test_render_inline_contains_details_and_footer():
    finding = f("SQL injection", severity="critical", ref="GEN-002", category="security")
    body = render_inline(finding)
    assert "**[CRITICAL · security] SQL injection**" in body
    assert "Rule: GEN-002" in body
    assert "fix it" in body
    assert body.endswith(footer(finding.fingerprint))


def test_render_summary_lists_counts_lows_overflow_skips_and_standards():
    plan = PublishPlan(
        inline=[f("crit", severity="critical")],
        summary_only=[f("minor", severity="low", file="b.py", line=4)],
        overflow=[f("extra", severity="medium", file="c.py", line=7)],
        previously_reported=2,
    )
    report = ReviewReport(
        source_commit="a" * 40,
        reviewed_files=["a.py", "b.py", "c.py"],
        skipped=[SkippedFile("README.md", "unsupported file type")],
        partial=True,
        standards=STD,
        plan=plan,
    )
    body = render_summary(report)
    assert "aaaaaaaaaaaa" in body
    assert "Reviewed 3 file(s)" in body
    assert "critical: 1" in body and "medium: 1" in body and "low: 1" in body
    assert "`b.py:4` minor" in body
    assert "`c.py:7` extra" in body
    assert "README.md: unsupported file type" in body
    assert "2 issue(s) already reported earlier were not repeated" in body
    assert "Partial review" in body
    assert "https://example/std.md (version abc123def456)" in body
    assert body.endswith(footer(commit_fingerprint("summary", "a" * 40)))


def test_render_summary_with_nothing_reviewable():
    plan = PublishPlan([], [], [], 0)
    report = ReviewReport("b" * 40, [], [SkippedFile("x.md", "unsupported file type")], False, STD, plan)
    body = render_summary(report)
    assert "No reviewable files" in body
    assert "x.md: unsupported file type" in body


def test_render_failure_mentions_request_id_and_has_failure_footer():
    body = render_failure("c" * 40, "req-123")
    assert "req-123" in body
    assert body.endswith(footer(commit_fingerprint("failure", "c" * 40)))


def test_long_bodies_are_truncated():
    huge = Finding("a.py", 1, "high", "bug", "t", "x" * 20_000, "y", None)
    body = render_inline(huge)
    assert len(body) <= MAX_COMMENT_CHARS
    assert "[comment truncated]" in body
    assert body.endswith(footer(huge.fingerprint))

    many = [SkippedFile(f"dir/file_{i:04}.txt", "unsupported file type") for i in range(2000)]
    report = ReviewReport("d" * 40, [], many, False, STD, PublishPlan([], [], [], 0))
    summary = render_summary(report)
    assert len(summary) <= MAX_COMMENT_CHARS
    assert summary.endswith(footer(commit_fingerprint("summary", "d" * 40)))


def test_fingerprint_only_counts_when_it_is_the_footer():
    pasted = "I disagree, see pr-reviewer · fp:0123456789ab in the middle"
    assert existing_fingerprints([pasted]) == set()


def test_repeated_rule_in_same_file_is_listed_not_lost():
    findings = [f("timeout missing", line=3, ref="PY-005"), f("timeout missing", line=9, ref="PY-005")]
    plan = plan_publication(findings, set(), max_inline=15, inline_severities=INLINE)
    assert [x.line for x in plan.inline] == [3]
    assert [x.line for x in plan.repeats] == [9]
    report = ReviewReport("e" * 40, ["a.py"], [], False, STD, plan)
    assert "`a.py:9` timeout missing" in render_summary(report)


def test_partial_review_with_nothing_reviewed_does_not_claim_nothing_reviewable():
    report = ReviewReport("f" * 40, [], [SkippedFile("a.py", "not reviewed: time limit reached")],
                          True, STD, PublishPlan([], [], [], 0))
    body = render_summary(report)
    assert "No reviewable files" not in body
    assert "No files were reviewed before the time limit" in body
