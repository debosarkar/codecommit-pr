"""Review findings: the model's output, validated and fingerprinted."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

SEVERITIES = ("critical", "high", "medium", "low")
CATEGORIES = ("bug", "security", "performance", "standards")


class InvalidFindings(ValueError):
    """The model's report_findings payload does not match the schema."""


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    severity: str
    category: str
    title: str
    explanation: str
    suggestion: str
    standard_ref: str | None = None

    @property
    def fingerprint(self) -> str:
        # Line is excluded so an issue that moves between pushes is not re-posted.
        key = self.standard_ref or _normalise(self.title)
        raw = f"{self.file}|{self.category}|{key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def severity_rank(severity: str) -> int:
    return SEVERITIES.index(severity)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def parse_findings(payload: object) -> list[Finding]:
    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
        raise InvalidFindings("payload must be an object with a 'findings' list")
    findings = []
    for index, item in enumerate(payload["findings"]):
        if not isinstance(item, dict):
            raise InvalidFindings(f"finding {index} is not an object")
        try:
            finding = Finding(
                file=str(item["file"]),
                line=int(item["line"]),
                severity=str(item["severity"]).lower(),
                category=str(item["category"]).lower(),
                title=str(item["title"]).strip(),
                explanation=str(item["explanation"]).strip(),
                suggestion=str(item.get("suggestion") or "").strip(),
                standard_ref=str(item["standard_ref"]) if item.get("standard_ref") else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidFindings(f"finding {index}: {exc!r}") from exc
        if finding.severity not in SEVERITIES:
            raise InvalidFindings(f"finding {index}: unknown severity {finding.severity!r}")
        if finding.category not in CATEGORIES:
            raise InvalidFindings(f"finding {index}: unknown category {finding.category!r}")
        findings.append(finding)
    return findings


def validate_findings(
    findings: list[Finding], changed_lines: dict[str, frozenset[int]]
) -> tuple[list[Finding], list[Finding]]:
    """Keep findings that point at an added/modified AFTER line of a reviewed file."""
    kept, dropped = [], []
    for finding in findings:
        if finding.line in changed_lines.get(finding.file, frozenset()):
            kept.append(finding)
        else:
            dropped.append(finding)
    return kept, dropped
