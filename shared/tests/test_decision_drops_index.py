"""Renderer rules for the decision-drops ``INDEX.md`` — parsing/rendering only.

Call sites, writing mechanics, and the deliberate absence of churn/CI-drift
machinery (INDEX.md itself is gitignored; the directory it lists is tracked)
live in ``test_decision_drops_index_producers.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.decision_drops_index import (
    _pending_drops,
    render_decision_drops_index,
    render_recent_drops_summary,
)


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


def test_recent_summary_bounds_to_the_limit_most_recent(tmp_path):
    dd = tmp_path / "decision-drops"
    for i in range(25):
        _drop(dd, f"iterate-x_{i:03d}.json")
    out = render_recent_drops_summary(dd, limit=20)
    for i in range(5):  # the 5 oldest are dropped
        assert f"iterate-x_{i:03d}.json" not in out
    for i in range(5, 25):  # the 20 most recent survive
        assert f"iterate-x_{i:03d}.json" in out
    assert out.count("\n") == 19  # 20 lines, 19 newlines between them


def test_recent_summary_empty_when_no_drops(tmp_path):
    dd = tmp_path / "decision-drops"
    dd.mkdir()
    assert render_recent_drops_summary(dd) == ""


def test_recent_summary_orders_by_date_not_by_filename(tmp_path):
    """A campaign sub-iterate's ``trg-*`` run_id sorts alphabetically AFTER a
    date-prefixed ``iterate-*`` one despite being the older drop — filename
    order would wrongly keep it as "most recent" and evict the actually-newer
    ``iterate-*`` drop instead. The drop's own `date` field is the only thing
    that reflects real recency."""
    dd = tmp_path / "decision-drops"
    _drop(dd, "trg-88621183_001.json", date="2026-08-06")
    _drop(dd, "iterate-x_001.json", date="2026-08-08")
    out = render_recent_drops_summary(dd, limit=1)
    assert "iterate-x_001.json" in out
    assert "trg-88621183_001.json" not in out
