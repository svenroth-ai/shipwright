"""Drift-guard: shared/config/gate_catalog.md must equal the generated render (SS2).

The doc is GENERATED from the gate_catalog.json beside it — never hand-edited.
It lives next to its source, not under docs/, because docs/ holds hand-written
instructions (CLAUDE.md "Where documents live").  If this fails, regenerate:

    uv run shared/scripts/tools/resolve_gate_policy.py --render-doc > shared/config/gate_catalog.md
"""
from __future__ import annotations

from pathlib import Path

from lib.gate_policy import load_catalog, render_catalog_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC_PATH = _REPO_ROOT / "shared" / "config" / "gate_catalog.md"


def test_doc_exists():
    assert _DOC_PATH.is_file(), "shared/config/gate_catalog.md is missing — generate it"


def test_doc_lives_beside_its_source():
    """The render sits next to the JSON it renders, never under docs/.

    Pins the placement decision (CLAUDE.md "Where documents live"): docs/ holds
    hand-written instructions, so a generated file kept in the tree lives beside
    its source.  Without this, a future move back to docs/ would still satisfy
    the byte-equality test below and silently undo the rule.
    """
    assert _DOC_PATH.parent == (_REPO_ROOT / "shared" / "config")
    assert not (_REPO_ROOT / "docs" / "gate-catalog.md").exists()


def test_doc_matches_generated_catalog():
    expected = render_catalog_markdown(load_catalog())
    actual = _DOC_PATH.read_text(encoding="utf-8")  # normalises CRLF -> LF on read
    assert actual == expected, (
        "shared/config/gate_catalog.md is stale. Regenerate:\n"
        "  uv run shared/scripts/tools/resolve_gate_policy.py --render-doc"
        " > shared/config/gate_catalog.md"
    )
