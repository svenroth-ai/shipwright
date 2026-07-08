"""Drift guard: the /shipwright-run master SKILL.md documents the additive
pipeline ``mode`` selection (Campaign 2026-07-07, SS1).

Locks the invariant that Step 3 offers the mode choice and Step 4 threads it
into ``write-config --mode``. SS8 (2026-07-08): ``single_session`` is now the
documented default and ``multi_session`` is deprecated — this guards that a
future edit can't silently drop either the selection or the new default.
"""
from pathlib import Path


def _skill_text(plugin_root: Path) -> str:
    return (plugin_root / "skills" / "run" / "SKILL.md").read_text(encoding="utf-8")


def test_skill_documents_both_modes(plugin_root):
    text = _skill_text(plugin_root)
    assert "multi_session" in text and "single_session" in text, (
        "SKILL.md must document both pipeline modes"
    )


def test_skill_marks_single_session_default(plugin_root):
    text = _skill_text(plugin_root)
    assert "single_session (default)" in text, (
        "SKILL.md must mark single_session as the default (SS8)"
    )
    assert "multi_session (deprecated)" in text, (
        "SKILL.md must mark multi_session as deprecated (SS8)"
    )


def test_step4_threads_mode_flag(plugin_root):
    text = _skill_text(plugin_root)
    assert "--mode" in text, "Step 4 write-config must pass --mode"


def test_step3_offers_change_mode(plugin_root):
    text = _skill_text(plugin_root)
    assert "Change mode" in text, (
        "Step 3 AskUserQuestion must offer a Change mode option"
    )


def test_skill_stays_within_runtime_prompt_budget(plugin_root):
    """Runtime-prompt files target <= 400 lines (constitution). The mode docs
    are deliberately compact so SKILL.md doesn't ratchet across the budget."""
    text = _skill_text(plugin_root)
    n = len(text.splitlines())
    assert n <= 400, f"run SKILL.md is {n} lines (> 400 runtime-prompt budget)"
