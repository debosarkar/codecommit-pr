import hashlib
import re
from pathlib import Path

import pytest

from pr_reviewer import standards as st

URL = "https://raw.githubusercontent.com/example/nda-skills/main/standards/code-review.md"


@pytest.fixture(autouse=True)
def _clear():
    st.clear_cache()
    yield
    st.clear_cache()


def test_fetches_and_reports_version():
    s = st.load_standards(URL, fetch=lambda url, timeout: "# rules\nGEN-001")
    assert s.text == "# rules\nGEN-001"
    assert s.source == URL
    assert s.version == hashlib.sha256(b"# rules\nGEN-001").hexdigest()[:12]


def test_caches_within_ttl_and_refetches_after():
    calls = []
    clock = [0.0]

    def fetch(url, timeout):
        calls.append(url)
        return f"v{len(calls)}"

    assert st.load_standards(URL, fetch=fetch, now=lambda: clock[0]).text == "v1"
    clock[0] = 599
    assert st.load_standards(URL, fetch=fetch, now=lambda: clock[0]).text == "v1"
    clock[0] = 601
    assert st.load_standards(URL, fetch=fetch, now=lambda: clock[0]).text == "v2"


def test_falls_back_to_bundled_default_and_does_not_cache_failure():
    def broken(url, timeout):
        raise OSError("network down")

    s = st.load_standards(URL, fetch=broken)
    assert s.source == st.BUILT_IN_SOURCE
    assert "GEN-001" in s.text
    assert st.load_standards(URL, fetch=lambda u, t: "fresh").text == "fresh"


def test_empty_download_falls_back():
    s = st.load_standards(URL, fetch=lambda u, t: "   ")
    assert s.source == st.BUILT_IN_SOURCE


def test_bundled_default_matches_repo_standards_and_rule_ids_are_unique():
    root = Path(__file__).resolve().parents[1]
    repo_doc = (root / "standards" / "code-review.md").read_text()
    bundled = (root / "src" / "pr_reviewer" / "default_standards.md").read_text()
    assert bundled == repo_doc
    ids = re.findall(r"^### ([A-Z]+-\d{3}) ", repo_doc, flags=re.MULTILINE)
    assert len(ids) == len(set(ids)) >= 20
