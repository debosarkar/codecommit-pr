"""Lambda entry point. Approach B (SQS) would replace only this module."""

from __future__ import annotations

import os

from pr_reviewer.codecommit_gateway import CodeCommitGateway
from pr_reviewer.log import log
from pr_reviewer.review_pipeline import Config, ReviewRequest, run_review
from pr_reviewer.reviewer import Reviewer
from pr_reviewer.standards import load_standards

SUPPORTED_EVENTS = {"pullRequestCreated", "pullRequestSourceBranchUpdated"}
_deps: tuple | None = None  # reused across warm invocations


def parse_event(event: dict) -> ReviewRequest | None:
    detail = event.get("detail") or {}
    if detail.get("event") not in SUPPORTED_EVENTS:
        return None
    repositories = detail.get("repositoryNames") or []
    if not repositories or not detail.get("pullRequestId"):
        return None
    return ReviewRequest(repositories[0], str(detail["pullRequestId"]), detail["event"])


def _default_deps(config: Config) -> tuple:
    import boto3
    from anthropic import AnthropicBedrockMantle

    gateway = CodeCommitGateway(boto3.client("codecommit"))
    claude = AnthropicBedrockMantle(aws_region=os.environ["AWS_REGION"], max_retries=4, timeout=120.0)
    return gateway, Reviewer(claude, config.model_id, effort=config.effort)


def lambda_handler(event: dict, context, deps: tuple | None = None) -> dict:
    global _deps
    config = Config.from_env(os.environ)
    request = parse_event(event)
    if request is None:
        log("ignored event", detailType=event.get("detail-type"), event=(event.get("detail") or {}).get("event"))
        return {"status": "ignored", "reason": "unsupported event"}
    if config.repository_names and request.repository not in config.repository_names:
        return {"status": "ignored", "reason": f"repository {request.repository} not in allow-list"}

    if deps is None:
        _deps = _deps or _default_deps(config)
        deps = _deps
    gateway, reviewer = deps
    log("review started", repository=request.repository, pullRequestId=request.pull_request_id, event=request.event)
    outcome = run_review(
        request,
        gateway=gateway,
        reviewer=reviewer,
        load_standards_fn=load_standards,
        config=config,
        remaining_ms=context.get_remaining_time_in_millis,
        request_id=context.aws_request_id,
    )
    return {"status": "done", "outcome": outcome}
