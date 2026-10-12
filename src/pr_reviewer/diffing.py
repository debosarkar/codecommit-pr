"""Line-numbered diffs. CodeCommit returns blobs, not patches, so we diff ourselves."""

from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass(frozen=True)
class FileDiff:
    path: str
    annotated_diff: str
    changed_lines: frozenset[int]  # added/modified line numbers in the AFTER version


def build_file_diff(path: str, before: str, after: str, context: int = 3) -> FileDiff:
    old = before.splitlines()
    new = after.splitlines()
    if old == new:
        return FileDiff(path, "", frozenset())

    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    out: list[str] = []
    changed: set[int] = set()
    for group in matcher.get_grouped_opcodes(context):
        a_start, a_end = group[0][1], group[-1][2]
        b_start, b_end = group[0][3], group[-1][4]
        out.append(f"@@ -{a_start + 1},{a_end - a_start} +{b_start + 1},{b_end - b_start} @@")
        for tag, a1, a2, b1, b2 in group:
            if tag == "equal":
                out.extend(f"  {k + 1:>5} | {new[k]}" for k in range(b1, b2))
                continue
            out.extend(f"-       | {old[k]}" for k in range(a1, a2))
            for k in range(b1, b2):
                out.append(f"+ {k + 1:>5} | {new[k]}")
                changed.add(k + 1)
    return FileDiff(path, "\n".join(out), frozenset(changed))
