"""Team coding standards: fetched from GitHub, cached briefly, bundled fallback."""

from __future__ import annotations

import hashlib
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pr_reviewer.log import log

BUILT_IN_SOURCE = "built-in default"
_DEFAULT_PATH = Path(__file__).with_name("default_standards.md")
_cache: dict[str, tuple[float, "Standards"]] = {}


@dataclass(frozen=True)
class Standards:
    text: str
    source: str
    version: str


def _version(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _http_get(url: str, timeout: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - fixed https URL from config
        return response.read().decode("utf-8")


def clear_cache() -> None:
    _cache.clear()


def load_standards(
    url: str,
    fetch: Callable[[str, float], str] = _http_get,
    now: Callable[[], float] = time.monotonic,
    ttl_seconds: float = 600,
) -> Standards:
    cached = _cache.get(url)
    if cached and now() - cached[0] < ttl_seconds:
        return cached[1]
    try:
        text = fetch(url, 5.0)
        if not text.strip():
            raise ValueError("standards document is empty")
    except Exception as exc:  # any fetch problem -> fallback, retried next invocation
        log("standards fetch failed; using built-in default", url=url, error=repr(exc))
        default = _DEFAULT_PATH.read_text(encoding="utf-8")
        return Standards(default, BUILT_IN_SOURCE, _version(default))
    standards = Standards(text, url, _version(text))
    _cache[url] = (now(), standards)
    return standards
