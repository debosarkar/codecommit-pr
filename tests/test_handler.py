import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pr_reviewer import handler
from pr_reviewer.review_pipeline import ReviewRequest

EVENTS = Path(__file__).parent / "events"


def load(name):
    return json.loads((EVENTS / name).read_text())


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "anthropic.claude-opus-5-5")
    monkeypatch.setenv("STANDARDS_URL", "https://example/std.md")
    monkeypatch.delenv("REPOSITORY_NAMES", raising=False)


CONTEXT = SimpleNamespace(aws_request_id="req-9", get_remaining_time_in_millis=lambda: 290_000)


@pytest.mark.parametrize("name,event", [
    ("pull_request_created.json", "pullRequestCreated"),
    ("source_branch_updated.json", "pullRequestSourceBranchUpdated"),
])
def test_parse_event(name, event):
    assert handler.parse_event(load(name)) == ReviewRequest("demo", "7", event)


def test_parse_event_ignores_other_events():
    e = load("pull_request_created.json")
    e["detail"]["event"] = "pullRequestMergeStatusUpdated"
    assert handler.parse_event(e) is None
    assert handler.parse_event({"detail": {}}) is None


def test_handler_runs_review_with_deps(env, monkeypatch):
    seen = {}

    def fake_run(request, **kw):
        seen["request"] = request
        seen["request_id"] = kw["request_id"]
        seen["remaining"] = kw["remaining_ms"]()
        return "reviewed: 0 inline comment(s)"

    monkeypatch.setattr(handler, "run_review", fake_run)
    result = handler.lambda_handler(load("pull_request_created.json"), CONTEXT, deps=("gw", "rv"))
    assert result == {"status": "done", "outcome": "reviewed: 0 inline comment(s)"}
    assert seen == {"request": ReviewRequest("demo", "7", "pullRequestCreated"),
                    "request_id": "req-9", "remaining": 290_000}


def test_handler_respects_repository_allow_list(env, monkeypatch):
    monkeypatch.setenv("REPOSITORY_NAMES", "other-repo")
    monkeypatch.setattr(handler, "run_review", lambda *a, **k: pytest.fail("should not run"))
    result = handler.lambda_handler(load("pull_request_created.json"), CONTEXT, deps=("gw", "rv"))
    assert result == {"status": "ignored", "reason": "repository demo not in allow-list"}


def test_handler_ignores_unsupported_event(env):
    e = load("pull_request_created.json")
    e["detail"]["event"] = "pullRequestStatusChanged"
    assert handler.lambda_handler(e, CONTEXT, deps=("gw", "rv")) == {"status": "ignored", "reason": "unsupported event"}
