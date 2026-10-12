"""Thin wrapper over the CodeCommit API calls the reviewer needs."""

from __future__ import annotations

from dataclasses import dataclass

from pr_reviewer.file_filter import ChangedFile


@dataclass(frozen=True)
class PullRequestInfo:
    pull_request_id: str
    repository: str
    status: str
    title: str
    source_commit: str
    destination_commit: str
    merge_base: str


class CodeCommitGateway:
    def __init__(self, client):
        self._cc = client

    def get_pull_request(self, pull_request_id: str) -> PullRequestInfo:
        pr = self._cc.get_pull_request(pullRequestId=pull_request_id)["pullRequest"]
        target = pr["pullRequestTargets"][0]
        return PullRequestInfo(
            pull_request_id=pull_request_id,
            repository=target["repositoryName"],
            status=pr["pullRequestStatus"],
            title=pr.get("title", ""),
            source_commit=target["sourceCommit"],
            destination_commit=target["destinationCommit"],
            merge_base=target.get("mergeBase") or target["destinationCommit"],
        )

    def get_differences(self, repository: str, before_commit: str, after_commit: str) -> list[ChangedFile]:
        kwargs = {
            "repositoryName": repository,
            "beforeCommitSpecifier": before_commit,
            "afterCommitSpecifier": after_commit,
        }
        files: list[ChangedFile] = []
        while True:
            response = self._cc.get_differences(**kwargs)
            for diff in response.get("differences", []):
                before = diff.get("beforeBlob") or {}
                after = diff.get("afterBlob") or {}
                files.append(ChangedFile(
                    path=after.get("path") or before["path"],
                    change_type=diff["changeType"],
                    before_blob_id=before.get("blobId"),
                    after_blob_id=after.get("blobId"),
                ))
            token = response.get("NextToken")
            if not token:
                return files
            kwargs["NextToken"] = token

    def get_blob(self, repository: str, blob_id: str) -> bytes:
        return self._cc.get_blob(repositoryName=repository, blobId=blob_id)["content"]

    def list_comment_bodies(self, pull_request_id: str) -> list[str]:
        kwargs = {"pullRequestId": pull_request_id}
        bodies: list[str] = []
        while True:
            response = self._cc.get_comments_for_pull_request(**kwargs)
            for data in response.get("commentsForPullRequestData", []):
                bodies.extend(c.get("content", "") for c in data.get("comments", []) if not c.get("deleted"))
            token = response.get("nextToken")
            if not token:
                return bodies
            kwargs["nextToken"] = token

    def post_comment(
        self,
        pr: PullRequestInfo,
        content: str,
        idempotency_key: str,
        file_path: str | None = None,
        line: int | None = None,
    ) -> None:
        kwargs = {
            "pullRequestId": pr.pull_request_id,
            "repositoryName": pr.repository,
            "beforeCommitId": pr.destination_commit,
            "afterCommitId": pr.source_commit,
            "content": content,
            "clientRequestToken": idempotency_key,
        }
        if file_path is not None:
            kwargs["location"] = {"filePath": file_path, "filePosition": line, "relativeFileVersion": "AFTER"}
        self._cc.post_comment_for_pull_request(**kwargs)
