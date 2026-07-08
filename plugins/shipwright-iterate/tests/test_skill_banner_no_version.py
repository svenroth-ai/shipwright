"""Drift-protection test: the iterate intro banner carries no hardcoded version.

Rationale (iterate-2026-07-08-remove-iterate-banner-version): shipwright-iterate
was the ONLY plugin whose intro banner printed a version string
(``SHIPWRIGHT-ITERATE v0.3.0``). Nothing kept that string in sync — ``sync_check.py``
only guards ``plugin.json`` vs ``marketplace.json`` — so it silently drifted stale
(banner said v0.3.0 while the authoritative plugin version had advanced to 0.30.0).
The fix removes the version so iterate matches all other plugins (whose banners
carry no version) and can never drift again.

This test locks that in: the H1 heading and the ``SHIPWRIGHT-ITERATE`` intro-banner
title line MUST NOT contain a ``vX.Y`` version token. It is intentionally scoped to
those two lines so legitimate version references elsewhere in the file (e.g. an
"External review (v0.5.x+)" feature-gating note) are not matched.
"""

import re
from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "iterate"
    / "SKILL.md"
)

# Matches a semver-ish version token like "v0.3.0" or "v0.30" (with optional patch).
_VERSION_TOKEN = re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b")


def _lines() -> list[str]:
    return SKILL_PATH.read_text(encoding="utf-8").splitlines()


def test_h1_heading_has_no_version() -> None:
    h1 = [ln for ln in _lines() if ln.startswith("# Shipwright Iterate Skill")]
    assert h1, "H1 heading '# Shipwright Iterate Skill' not found"
    for ln in h1:
        assert not _VERSION_TOKEN.search(ln), (
            f"iterate H1 heading must not hardcode a version (drifts stale): {ln!r}"
        )


def test_intro_banner_title_has_no_version() -> None:
    banner = [ln for ln in _lines() if ln.startswith("SHIPWRIGHT-ITERATE")]
    assert banner, "Intro-banner title line 'SHIPWRIGHT-ITERATE...' not found"
    for ln in banner:
        assert not _VERSION_TOKEN.search(ln), (
            f"iterate intro banner must not hardcode a version (drifts stale): {ln!r}"
        )
