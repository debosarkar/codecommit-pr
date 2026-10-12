"""Score the bot's inline comments on the demo PR against demo/expected.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

FOOTER = "pr-reviewer · fp:"


def score(expected: list[dict], comments: list[dict]) -> dict:
    found: set[str] = set()
    noise = 0
    for c in comments:
        hits = [e["id"] for e in expected
                if e["file"] == c["file"] and e["lines"][0] <= c["line"] <= e["lines"][1]]
        if hits:
            found.update(hits)
        else:
            noise += 1
    ids = [e["id"] for e in expected]
    return {
        "found": [i for i in ids if i in found],
        "missed": [i for i in ids if i not in found],
        "noise": noise,
        "recall": round(len(found) / len(ids), 2) if ids else 0.0,
    }


def _bot_inline_comments(pull_request_id: str) -> list[dict]:
    import boto3

    cc = boto3.client("codecommit")
    kwargs = {"pullRequestId": pull_request_id}
    out = []
    while True:
        resp = cc.get_comments_for_pull_request(**kwargs)
        for data in resp.get("commentsForPullRequestData", []):
            loc = data.get("location")
            if not loc:
                continue
            for c in data.get("comments", []):
                if FOOTER in c.get("content", ""):
                    out.append({"file": loc["filePath"].split("/")[-1], "line": loc["filePosition"]})
        if not resp.get("nextToken"):
            return out
        kwargs["nextToken"] = resp["nextToken"]


if __name__ == "__main__":
    expected = json.loads((Path(__file__).resolve().parents[1] / "demo" / "expected.json").read_text())
    print(json.dumps(score(expected, _bot_inline_comments(sys.argv[1])), indent=2))
