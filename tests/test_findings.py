import pytest

from pr_reviewer.findings import (
    Finding,
    InvalidFindings,
    parse_findings,
    severity_rank,
    validate_findings,
)


def _raw(**overrides):
    item = {
        "file": "app/orders.py",
        "line": 12,
        "severity": "high",
        "category": "security",
        "title": "SQL injection via f-string",
        "explanation": "User input is interpolated into SQL.",
        "suggestion": "Use parameterised queries.",
        "standard_ref": "PY-002",
    }
    item.update(overrides)
    return item


def test_parse_findings_builds_findings():
    findings = parse_findings({"findings": [_raw()]})
    assert findings == [
        Finding(
            file="app/orders.py",
            line=12,
            severity="high",
            category="security",
            title="SQL injection via f-string",
            explanation="User input is interpolated into SQL.",
            suggestion="Use parameterised queries.",
            standard_ref="PY-002",
        )
    ]


def test_parse_findings_normalises_case_and_null_ref():
    [f] = parse_findings({"findings": [_raw(severity="HIGH", category="Bug", standard_ref=None)]})
    assert f.severity == "high"
    assert f.category == "bug"
    assert f.standard_ref is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"findings": "nope"},
        {"findings": ["not-an-object"]},
        {"findings": [_raw(severity="urgent")]},
        {"findings": [_raw(category="style")]},
        {"findings": [_raw(line="twelve")]},
        {"findings": [{k: v for k, v in _raw().items() if k != "file"}]},
    ],
)
def test_parse_findings_rejects_malformed(payload):
    with pytest.raises(InvalidFindings):
        parse_findings(payload)


def test_empty_findings_list_is_valid():
    assert parse_findings({"findings": []}) == []


def test_fingerprint_is_stable_and_ignores_line_and_wording_noise():
    a = parse_findings({"findings": [_raw(standard_ref=None, title="SQL injection via f-string")]})[0]
    b = parse_findings({"findings": [_raw(standard_ref=None, line=40, title="  sql INJECTION via f-string! ")]})[0]
    assert a.fingerprint == b.fingerprint
    assert len(a.fingerprint) == 12
    assert all(c in "0123456789abcdef" for c in a.fingerprint)


def test_fingerprint_prefers_standard_ref_over_title():
    a = parse_findings({"findings": [_raw(title="one wording")]})[0]
    b = parse_findings({"findings": [_raw(title="other wording")]})[0]
    assert a.fingerprint == b.fingerprint


def test_fingerprint_differs_by_file():
    a = parse_findings({"findings": [_raw(file="a.py")]})[0]
    b = parse_findings({"findings": [_raw(file="b.py")]})[0]
    assert a.fingerprint != b.fingerprint


def test_severity_rank_orders_critical_first():
    assert [severity_rank(s) for s in ("critical", "high", "medium", "low")] == [0, 1, 2, 3]


def test_validate_findings_keeps_only_changed_lines_in_known_files():
    good = parse_findings({"findings": [_raw(line=12)]})[0]
    context_line = parse_findings({"findings": [_raw(line=13)]})[0]
    unknown_file = parse_findings({"findings": [_raw(file="other.py")]})[0]
    kept, dropped = validate_findings(
        [good, context_line, unknown_file], {"app/orders.py": frozenset({12})}
    )
    assert kept == [good]
    assert dropped == [context_line, unknown_file]
