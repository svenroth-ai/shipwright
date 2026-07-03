"""Empirical calibration suite — real OSS repos, opt-in (``-m empirical``).

Excluded from the hermetic default run and from the PR gate; a dedicated CI job
(network + gh) runs it and it **gates the public launch** (G5). In G1 the
manifest is seeded but SHAs are ``PENDING-G5``, so every entry skips *loudly*
(never silently) with the reason — the harness is proven, the real-repo
calibration + gate land in G5.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

import replay  # noqa: E402

pytestmark = pytest.mark.empirical

_MANIFEST = Path(__file__).resolve().parent / "repos.yaml"


def _manifest_entries() -> list[dict]:
    data = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))
    return data["repos"]


def _allow_network() -> bool:
    return os.environ.get("SHIPWRIGHT_GRADE_ALLOW_NETWORK", "").lower() in ("1", "true")


@pytest.mark.parametrize("entry", _manifest_entries(), ids=lambda e: e["name"])
def test_real_repo_grade_matches_band(entry: dict):
    sha = str(entry["pinned_sha"])
    if not replay.is_pinned_sha(sha):
        pytest.skip(
            f"{entry['name']}: pinned_sha is a G5 placeholder ({sha!r}); "
            "real SHA pinning + payload recording land in G5"
        )
    cached = replay.replay(f"{entry['name']}@{sha}")
    if cached is None and not _allow_network():
        pytest.skip(
            f"{entry['name']}: no cached payload and network disabled "
            "(set SHIPWRIGHT_GRADE_ALLOW_NETWORK=1 to record)"
        )
    # G5 wires the fetch → project → grade path and asserts the band + ordering.
    assert cached is not None
    assert cached.get("grade") in {"A", "B", "C", "D", "F"}
