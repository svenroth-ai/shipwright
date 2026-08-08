"""Renderer rules for the decision-drops ``INDEX.md`` — parsing/rendering only.

Call sites, writing mechanics, and the deliberate absence of churn/CI-drift
machinery (the directory is gitignored) live in
``test_decision_drops_index_producers.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.decision_drops_index import _pending_drops, render_decision_drops_index


def _drop(dd: Path, name: str, **fields) -> Path:
    dd.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": "iterate-x", "section": "Iterate — change: x",
        "title": "T", "date": "2026-08-07", "decision": "did the thing",
    }
    payload.update(fields)
    path = dd / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_no_drops_renders_the_empty_state(tmp_path):
    dd = tmp_path / "decision-drops"
    dd.mkdir()
    out = render_decision_drops_index(dd)
    assert "No pending decision-drops" in out


def test_a_pending_drop_is_listed(tmp_path):
    dd = tmp_path / "decision-drops"
    _drop(dd, "iterate-x_001.json", title="My decision")
    out = render_decision_drops_index(dd)
    assert "iterate-x_001.json" in out
    assert "My decision" in out


def test_missing_title_falls_back_to_a_decision_snippet(tmp_path):
    dd = tmp_path / "decision-drops"
    _drop(dd, "iterate-x_001.json", title="", decision="a" * 100)
    out = render_decision_drops_index(dd)
    assert ("a" * 60) in out
    assert ("a" * 61) not in out


def test_a_null_decision_with_no_title_does_not_raise(tmp_path):
    """title-fallback slices `decision` — it must stringify first, or a valid
    JSON drop with `"decision": null` raises TypeError instead of rendering."""
    dd = tmp_path / "decision-drops"
    _drop(dd, "iterate-x_001.json", title="", decision=None)
    out = render_decision_drops_index(dd)
    assert "iterate-x_001.json" in out


def test_scaffolding_files_are_skipped(tmp_path):
    dd = tmp_path / "decision-drops"
    dd.mkdir()
    (dd / ".gitkeep").write_text("", encoding="utf-8")
    (dd / "_scratch.json").write_text("{}", encoding="utf-8")
    assert _pending_drops(dd) == []


def test_a_malformed_drop_is_skipped_not_fatal(tmp_path):
    dd = tmp_path / "decision-drops"
    dd.mkdir()
    (dd / "broken.json").write_text("not json", encoding="utf-8")
    _drop(dd, "good_001.json")
    out = render_decision_drops_index(dd)
    assert "good_001.json" in out
    assert "broken" not in out


def test_render_is_lf_only(tmp_path):
    dd = tmp_path / "decision-drops"
    _drop(dd, "iterate-x_001.json")
    assert "\r" not in render_decision_drops_index(dd)


def test_an_embedded_newline_in_a_title_cannot_break_the_bullet_row(tmp_path):
    dd = tmp_path / "decision-drops"
    _drop(dd, "iterate-x_001.json", title="Line one\nLine two")
    out = render_decision_drops_index(dd)
    assert "- `iterate-x_001.json` — 2026-08-07 — Iterate — change: x — Line one Line two" in out


def test_markdown_syntax_in_a_title_cannot_become_a_live_link_or_image(tmp_path):
    dd = tmp_path / "decision-drops"
    _drop(dd, "iterate-x_001.json", title="![tracking](https://example.invalid/x)")
    out = render_decision_drops_index(dd)
    assert "![tracking](https://example.invalid/x)" not in out
    assert r"\[tracking\]\(https://example.invalid/x\)" in out
