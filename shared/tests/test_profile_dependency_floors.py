"""Pinned regression test for shared/profiles/vite-hono.json's hono floor.

hono < 4.12.34 is vulnerable to CVE-2026-69207/-71848/-71849/-71850. The
profile shipped ``"hono": "^4.7.0"`` until this iterate
(iterate-2026-08-17-vite-hono-floor); shipwright-webui and leadwright each
independently hand-patched their own copies without the source profile ever
changing. A hand-maintained registry + generic checker was considered and
built, but architecture review (two independent reviewers, `--mode
architecture`) concluded that was more standing machinery than one known
stale floor justifies — see the ADR
(``.shipwright/planning/adr/iterate-2026-08-17-vite-hono-floor-profile-floor-drift.md``).
This single pinned assertion is the accepted narrower alternative: a future
vulnerable floor gets fixed directly and pinned with its own test at
discovery time, the same way this one is.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VITE_HONO_PROFILE = _REPO_ROOT / "shared" / "profiles" / "vite-hono.json"

#: The CVE fix line this test pins the declared floor against.
_HONO_MIN_SAFE_VERSION = (4, 12, 34)

_DECLARED_HONO_FLOOR = json.loads(_VITE_HONO_PROFILE.read_text(encoding="utf-8"))["stack"][
    "backend"
]["hono"]


def _floor(range_str: str) -> tuple[int, ...]:
    """Extract the minimum resolvable version from a simple caret/tilde/exact
    npm range. Deliberately narrow (this profile has only ever declared
    plain caret ranges) — see the ADR for why a general range parser was
    rejected as disproportionate to a single pinned entry."""
    m = re.fullmatch(r"(?:\^|~)?(\d+(?:\.\d+)*)", range_str.strip())
    assert m, f"unexpected hono range shape {range_str!r} — update this test's parsing"
    return tuple(int(part) for part in m.group(1).split("."))


@pytest.mark.parametrize(
    ("declared_range", "meets_fix_line"),
    [
        pytest.param(_DECLARED_HONO_FLOOR, True, id="current-profile"),
        pytest.param("^4.7.0", False, id="pre-fix-vulnerable-value"),
    ],
)
def test_hono_floor_meets_the_cve_fix_line(declared_range, meets_fix_line):
    """Same read+compare path for both cases: the real, shipped profile must
    never regress below the fix line, and the exact pre-fix value (^4.7.0)
    must compare as BELOW it — this is what would have failed before
    shared/profiles/vite-hono.json was raised to ^4.12.34."""
    assert (_floor(declared_range) >= _HONO_MIN_SAFE_VERSION) is meets_fix_line
