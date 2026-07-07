"""Drift-guard: docs/gate-catalog.md must equal the generated render (SS2).

The doc is GENERATED from shared/config/gate_catalog.json — never hand-edited.
If this fails, regenerate:

    uv run shared/scripts/tools/resolve_gate_policy.py --render-doc > docs/gate-catalog.md
"""
from __future__ import annotations

from pathlib import Path

from lib.gate_policy import load_catalog, render_catalog_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC_PATH = _REPO_ROOT / "docs" / "gate-catalog.md"


def test_doc_exists():
    assert _DOC_PATH.is_file(), "docs/gate-catalog.md is missing — generate it"


def test_doc_matches_generated_catalog():
    expected = render_catalog_markdown(load_catalog())
    actual = _DOC_PATH.read_text(encoding="utf-8")  # normalises CRLF -> LF on read
    assert actual == expected, (
        "docs/gate-catalog.md is stale. Regenerate:\n"
        "  uv run shared/scripts/tools/resolve_gate_policy.py --render-doc > docs/gate-catalog.md"
    )
