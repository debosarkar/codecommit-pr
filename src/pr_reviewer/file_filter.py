"""Decide which changed files are worth sending to the model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

LANGUAGES = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
}
GENERATED_DIRS = {"node_modules", "dist", "build", "target", "generated", "__generated__", ".gradle", "vendor"}
GENERATED_SUFFIXES = (".min.js", ".bundle.js", ".d.ts")


@dataclass(frozen=True)
class ChangedFile:
    path: str
    change_type: str  # CodeCommit changeType: "A" | "M" | "D"
    before_blob_id: str | None
    after_blob_id: str | None


@dataclass(frozen=True)
class SkippedFile:
    path: str
    reason: str


def language_for(path: str) -> str | None:
    return LANGUAGES.get(PurePosixPath(path).suffix.lower())


def _path_skip_reason(f: ChangedFile) -> str | None:
    if f.change_type == "D" or f.after_blob_id is None:
        return "deleted"
    if language_for(f.path) is None:
        return "unsupported file type"
    p = PurePosixPath(f.path)
    if GENERATED_DIRS.intersection(p.parts[:-1]) or p.name.endswith(GENERATED_SUFFIXES):
        return "generated or vendored"
    if f.before_blob_id is not None and f.before_blob_id == f.after_blob_id:
        return "renamed or mode change without content changes"
    return None


def select_files(files: list[ChangedFile], max_files: int) -> tuple[list[ChangedFile], list[SkippedFile]]:
    selected: list[ChangedFile] = []
    skipped: list[SkippedFile] = []
    for f in sorted(files, key=lambda f: f.path):
        reason = _path_skip_reason(f)
        if reason:
            skipped.append(SkippedFile(f.path, reason))
        elif len(selected) >= max_files:
            skipped.append(SkippedFile(f.path, f"not reviewed: over the {max_files}-file limit"))
        else:
            selected.append(f)
    return selected, skipped


def content_skip_reason(content: bytes, max_bytes: int) -> str | None:
    if len(content) > max_bytes:
        return f"larger than {max_bytes} bytes"
    if b"\x00" in content[:8192]:
        return "binary file"
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return "not UTF-8 text"
    return None
