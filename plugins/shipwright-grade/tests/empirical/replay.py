"""replay — record/replay cache for the empirical suite (Gemini #1).

GitHub deletes run logs/artifacts (~90 days), so live fetches for pinned SHAs
would rot the suite. The fix: on first run, cache the fetched payload under
``tests/empirical/fixtures/`` and thereafter **replay from cache** — deterministic,
network only to refresh. This module is the cache primitive; the network fetch
itself is wired in G5.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def is_pinned_sha(sha: str) -> bool:
    """True only for a real 40-hex commit SHA (placeholders are excluded)."""
    return bool(_SHA_RE.match(sha.strip().lower()))


def _safe_key(key: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]", "_", key)


def cache_path(key: str, *, cache_dir: Path = FIXTURES_DIR) -> Path:
    return cache_dir / f"{_safe_key(key)}.json"


def replay(key: str, *, cache_dir: Path = FIXTURES_DIR) -> dict[str, Any] | None:
    path = cache_path(key, cache_dir=cache_dir)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def record(key: str, payload: dict[str, Any], *, cache_dir: Path = FIXTURES_DIR) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(key, cache_dir=cache_dir)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
                    encoding="utf-8")
    return path


def load_or_record(
    key: str,
    fetch_fn: Callable[[], dict[str, Any]],
    *,
    allow_network: bool,
    cache_dir: Path = FIXTURES_DIR,
) -> dict[str, Any] | None:
    """Return the cached payload; else fetch+cache when ``allow_network``; else None."""
    cached = replay(key, cache_dir=cache_dir)
    if cached is not None:
        return cached
    if not allow_network:
        return None
    payload = fetch_fn()
    record(key, payload, cache_dir=cache_dir)
    return payload
