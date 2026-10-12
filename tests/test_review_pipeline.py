import pytest

from pr_reviewer.codecommit_gateway import PullRequestInfo
from pr_reviewer.file_filter import ChangedFile
from pr_reviewer.findings import Finding
from pr_reviewer.publisher import commit_fingerprint, footer
from pr_reviewer.review_pipeline import Config, ReviewRequest, run_review
from pr_reviewer.standards import Standards

SRC, DST, BASE = "a" * 40, "b" * 40, "c" * 40
STD = Standards("rules", "https://example/std.md", "abc123def456")
REQ = ReviewRequest("demo", "7", "pullRequestCreated")


class FakeGateway:
    def __init__(self, files, blobs, status="OPEN", existing=()):
        self.pr = PullRequestInfo("7", "demo", status, "t", SRC, DST, BASE)
        self.files = files
        self.blobs = blobs
        self.existing = list(existing)
        self.posted = []  # (content, key, file_path, line)

    def get_pull_request(self, pr_id):
        return self.pr

    def get_differences(self, repo, before, after):
        assert (before, after) == (BASE, SRC)
        return self.files

    def get_blob(self, repo, blob_id):
        return self.blobs[blob_id]

    def list_comment_bodies(self, pr_id):
        return self.existing + [p[0] for p in self.posted]

    def post_comment(self, pr, content, idempotency_key, file_path=None, line=None):
        self.posted.append((content, idempotency_key, file_path, line))


class FakeReviewer:
    def __init__(self, results):
        self.results = list(results)
        self.batches = []

    def review_batch(self, standards, batch, time_budget_s=None):
        self.batches.append([f.path for f in batch])
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def cfg(**kw):
    return Config(model_id="m", standards_url="https://example/std.md", **kw)


def run(gw, reviewer, remaining=lambda: 300_000, **cfg_kw):
    return run_review(REQ, gateway=gw, reviewer=reviewer, load_standards_fn=lambda url: STD,
                      config=cfg(**cfg_kw), remaining_ms=remaining, request_id="req-1")


def finding(line=1, severity="high", title="bug here", file="app.py"):
    return Finding(file, line, severity, "bug", title, "e", "s", None)


def test_happy_path_posts_inline_and_summary():
    gw = FakeGateway([ChangedFile("app.py", "A", None, "n1")], {"n1": b"x = 1\ny = 2\n"})
    reviewer = FakeReviewer([[finding(line=2), finding(line=99, title="hallucinated")]])
    outcome = run(gw, reviewer)
    inline = [p for p in gw.posted if p[2]]
    general = [p for p in gw.posted if not p[2]]
    assert [(p[2], p[3]) for p in inline] == [("app.py", 2)]
    assert inline[0][1] == f"{finding(line=2).fingerprint}-{SRC[:12]}"
    assert len(general) == 1 and "Automated review" in general[0][0]
    assert outcome == "reviewed: 1 inline comment(s)"


def test_rerun_does_not_duplicate_comments():
    gw = FakeGateway([ChangedFile("app.py", "A", None, "n1")], {"n1": b"x = 1\n"})
    run(gw, FakeReviewer([[finding()]]))
    first = len(gw.posted)
    run(gw, FakeReviewer([[finding()]]))
    assert len(gw.posted) == first


def test_closed_pr_is_skipped():
    gw = FakeGateway([], {}, status="CLOSED")
    assert run(gw, FakeReviewer([])) == "skipped: pull request is CLOSED"
    assert gw.posted == []


def test_no_reviewable_files_posts_single_summary():
    gw = FakeGateway([ChangedFile("README.md", "M", "o1", "n1")], {})
    reviewer = FakeReviewer([])
    run(gw, reviewer)
    run(gw, reviewer)
    assert reviewer.batches == []
    assert len(gw.posted) == 1
    assert "No reviewable files" in gw.posted[0][0]
    assert "README.md: unsupported file type" in gw.posted[0][0]


def test_binary_and_unchanged_content_are_skipped_with_reasons():
    gw = FakeGateway(
        [ChangedFile("bin.py", "A", None, "b1"), ChangedFile("same.py", "M", "o2", "n2")],
        {"b1": b"\x00\x01", "o2": b"x = 1", "n2": b"x = 1\n"},
    )
    reviewer = FakeReviewer([])
    run(gw, reviewer)
    summary = gw.posted[-1][0]
    assert "bin.py: binary file" in summary
    assert "same.py: no added or modified lines" in summary
    assert reviewer.batches == []


def test_failed_batch_is_reported_and_others_continue(monkeypatch):
    import pr_reviewer.review_pipeline as rp
    monkeypatch.setattr(rp, "build_batches", lambda files: [[f] for f in files])
    gw = FakeGateway(
        [ChangedFile("a.py", "A", None, "n1"), ChangedFile("b.py", "A", None, "n2")],
        {"n1": b"a = 1\n", "n2": b"b = 1\n"},
    )
    reviewer = FakeReviewer([RuntimeError("throttled"), [finding(file="b.py")]])
    run(gw, reviewer)
    summary = gw.posted[-1][0]
    assert "a.py: review failed (RuntimeError)" in summary
    assert any(p[2] == "b.py" for p in gw.posted)


def test_time_budget_stops_early_and_marks_partial(monkeypatch):
    import pr_reviewer.review_pipeline as rp
    monkeypatch.setattr(rp, "build_batches", lambda files: [[f] for f in files])
    gw = FakeGateway(
        [ChangedFile("a.py", "A", None, "n1"), ChangedFile("b.py", "A", None, "n2")],
        {"n1": b"a = 1\n", "n2": b"b = 1\n"},
    )
    clock = iter([200_000, 200_000, 30_000])  # batch 1: check + budget; batch 2: check
    reviewer = FakeReviewer([[]])
    run(gw, reviewer, remaining=lambda: next(clock))
    assert reviewer.batches == [["a.py"]]
    summary = gw.posted[-1][0]
    assert "Partial review" in summary
    assert "b.py: not reviewed: time limit reached" in summary


def test_unexpected_error_posts_failure_comment_once_and_reraises():
    class Boom(FakeGateway):
        def get_differences(self, *a):
            raise RuntimeError("codecommit down")

    gw = Boom([], {})
    for _ in range(2):
        with pytest.raises(RuntimeError):
            run(gw, FakeReviewer([]))
    assert len(gw.posted) == 1
    assert gw.posted[0][0].endswith(footer(commit_fingerprint("failure", SRC)))
    assert "req-1" in gw.posted[0][0]


def test_config_from_env():
    c = Config.from_env({
        "MODEL_ID": "anthropic.claude-opus-5-5", "STANDARDS_URL": "https://x/s.md",
        "REPOSITORY_NAMES": " a, b ,", "MAX_FILES": "10", "MAX_INLINE_COMMENTS": "5",
        "MAX_FILE_BYTES": "2000", "INLINE_SEVERITIES": "critical,high", "EFFORT": "xhigh",
    })
    assert c == Config("anthropic.claude-opus-5-5", "https://x/s.md", frozenset({"a", "b"}),
                       10, 5, 2000, frozenset({"critical", "high"}), "xhigh")
    d = Config.from_env({"MODEL_ID": "m", "STANDARDS_URL": "u"})
    assert d.repository_names == frozenset() and d.max_files == 30 and d.effort == "high"


class BudgetReviewer(FakeReviewer):
    def review_batch(self, standards, batch, time_budget_s=None):
        self.budgets = getattr(self, "budgets", []) + [time_budget_s]
        return super().review_batch(standards, batch, time_budget_s)


def test_reviewer_gets_time_budget_minus_publish_reserve():
    gw = FakeGateway([ChangedFile("app.py", "A", None, "n1")], {"n1": b"x = 1\n"})
    reviewer = BudgetReviewer([[]])
    run(gw, reviewer, remaining=lambda: 200_000)
    assert reviewer.budgets == [170.0]


def test_reviewer_budget_exhaustion_marks_partial():
    from pr_reviewer.reviewer import ReviewTimeBudgetExceeded

    gw = FakeGateway([ChangedFile("app.py", "A", None, "n1")], {"n1": b"x = 1\n"})
    run(gw, FakeReviewer([ReviewTimeBudgetExceeded("5s left")]))
    summary = gw.posted[-1][0]
    assert "Partial review" in summary
    assert "app.py: not reviewed: time limit reached" in summary


def test_all_batches_failing_is_a_failed_run_not_an_empty_review():
    gw = FakeGateway([ChangedFile("app.py", "A", None, "n1")], {"n1": b"x = 1\n"})
    with pytest.raises(RuntimeError, match="every review batch failed"):
        run(gw, FakeReviewer([PermissionError("AccessDenied")]))
    assert len(gw.posted) == 1
    assert "could not complete" in gw.posted[0][0]


class FlakyPostGateway(FakeGateway):
    def __init__(self, *a, fail=None, **kw):
        super().__init__(*a, **kw)
        self.fail = fail or {}

    def post_comment(self, pr, content, idempotency_key, file_path=None, line=None):
        if file_path in self.fail:
            raise self.fail[file_path]
        super().post_comment(pr, content, idempotency_key, file_path, line)


class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


def test_inline_post_errors_do_not_abort_publishing(monkeypatch):
    import pr_reviewer.review_pipeline as rp
    monkeypatch.setattr(rp, "build_batches", lambda files: [files])
    gw = FlakyPostGateway(
        [ChangedFile(p, "A", None, p) for p in ("a.py", "b.py", "c.py")],
        {p: b"x = 1\n" for p in ("a.py", "b.py", "c.py")},
        fail={"a.py": FakeClientError("IdempotencyParameterMismatchException"),
              "b.py": FakeClientError("InvalidFilePositionException")},
    )
    reviewer = FakeReviewer([[finding(file="a.py"), finding(file="b.py"), finding(file="c.py")]])
    outcome = run(gw, reviewer)
    assert [p[2] for p in gw.posted if p[2]] == ["c.py"]
    summary = gw.posted[-1][0]
    assert "`b.py:1` bug here" in summary      # unpostable finding surfaced in the summary
    assert "`a.py:1`" not in summary            # idempotency mismatch = already posted
    assert outcome == "reviewed: 1 inline comment(s)"
