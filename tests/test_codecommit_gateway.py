import boto3
import pytest
from botocore.stub import Stubber

from pr_reviewer.codecommit_gateway import CodeCommitGateway, PullRequestInfo
from pr_reviewer.file_filter import ChangedFile

SRC = "a" * 40
DST = "b" * 40
BASE = "c" * 40


@pytest.fixture
def stubbed():
    client = boto3.client("codecommit", region_name="us-east-1",
                          aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(client) as stub:
        yield CodeCommitGateway(client), stub
        stub.assert_no_pending_responses()


def _pr():
    return PullRequestInfo("7", "demo", "OPEN", "Add orders", SRC, DST, BASE)


def test_get_pull_request(stubbed):
    gw, stub = stubbed
    stub.add_response(
        "get_pull_request",
        {"pullRequest": {
            "pullRequestId": "7", "title": "Add orders", "pullRequestStatus": "OPEN",
            "pullRequestTargets": [{
                "repositoryName": "demo", "sourceReference": "refs/heads/feature",
                "sourceCommit": SRC, "destinationCommit": DST, "mergeBase": BASE,
            }],
        }},
        {"pullRequestId": "7"},
    )
    assert gw.get_pull_request("7") == _pr()


def test_get_differences_paginates_and_maps_blobs(stubbed):
    gw, stub = stubbed
    stub.add_response(
        "get_differences",
        {"differences": [{"afterBlob": {"blobId": "n1", "path": "new.py", "mode": "100644"}, "changeType": "A"}],
         "NextToken": "t1"},
        {"repositoryName": "demo", "beforeCommitSpecifier": BASE, "afterCommitSpecifier": SRC},
    )
    stub.add_response(
        "get_differences",
        {"differences": [
            {"beforeBlob": {"blobId": "o2", "path": "mod.py", "mode": "100644"},
             "afterBlob": {"blobId": "n2", "path": "mod.py", "mode": "100644"}, "changeType": "M"},
            {"beforeBlob": {"blobId": "o3", "path": "gone.py", "mode": "100644"}, "changeType": "D"},
        ]},
        {"repositoryName": "demo", "beforeCommitSpecifier": BASE, "afterCommitSpecifier": SRC, "NextToken": "t1"},
    )
    assert gw.get_differences("demo", BASE, SRC) == [
        ChangedFile("new.py", "A", None, "n1"),
        ChangedFile("mod.py", "M", "o2", "n2"),
        ChangedFile("gone.py", "D", "o3", None),
    ]


def test_get_blob(stubbed):
    gw, stub = stubbed
    stub.add_response("get_blob", {"content": b"print(1)\n"}, {"repositoryName": "demo", "blobId": "n1"})
    assert gw.get_blob("demo", "n1") == b"print(1)\n"


def test_list_comment_bodies_skips_deleted_and_paginates(stubbed):
    gw, stub = stubbed
    stub.add_response(
        "get_comments_for_pull_request",
        {"commentsForPullRequestData": [{"comments": [
            {"commentId": "1", "content": "first"},
            {"commentId": "2", "content": "", "deleted": True},
        ]}], "nextToken": "p2"},
        {"pullRequestId": "7"},
    )
    stub.add_response(
        "get_comments_for_pull_request",
        {"commentsForPullRequestData": [{"comments": [{"commentId": "3", "content": "second"}]}]},
        {"pullRequestId": "7", "nextToken": "p2"},
    )
    assert gw.list_comment_bodies("7") == ["first", "second"]


def test_post_inline_comment(stubbed):
    gw, stub = stubbed
    stub.add_response(
        "post_comment_for_pull_request", {},
        {"pullRequestId": "7", "repositoryName": "demo", "beforeCommitId": DST, "afterCommitId": SRC,
         "content": "body", "clientRequestToken": "key-1",
         "location": {"filePath": "new.py", "filePosition": 3, "relativeFileVersion": "AFTER"}},
    )
    gw.post_comment(_pr(), "body", "key-1", file_path="new.py", line=3)


def test_post_general_comment_has_no_location(stubbed):
    gw, stub = stubbed
    stub.add_response(
        "post_comment_for_pull_request", {},
        {"pullRequestId": "7", "repositoryName": "demo", "beforeCommitId": DST, "afterCommitId": SRC,
         "content": "summary", "clientRequestToken": "key-2"},
    )
    gw.post_comment(_pr(), "summary", "key-2")
