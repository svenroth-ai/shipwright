"""Drift guard: the /shipwright-run master SKILL.md documents a DRIVEN pipeline.

Replaces the two guards that pinned the removed multi-session model
(``test_run_skill_mode_selection.py`` — which required SKILL.md to offer a mode
CHOICE — and ``test_run_skill_handoff_banner.py`` — which required a surface-aware
``claude --session-id`` launch card). Both encoded the coordinator model that
``iterate-2026-07-14-remove-multi-session`` deleted, so they are replaced rather
than repaired: the master now DRIVES every phase from its own conversation.

These pin the inverse invariants — a future edit cannot silently reintroduce the
launch-card hand-off or a mode question.
"""
from pathlib import Path


def _skill_text(plugin_root: Path) -> str:
    return (plugin_root / "skills" / "run" / "SKILL.md").read_text(encoding="utf-8")


def test_skill_says_the_master_drives_the_pipeline(plugin_root):
    text = _skill_text(plugin_root).lower()
    assert "drive" in text, "SKILL.md must state that the master DRIVES the pipeline"
    assert "phase-runner" in text, (
        "SKILL.md must name the phase-runner subagent — the mechanism by which a "
        "phase runs inside the master's conversation"
    )


def test_skill_emits_no_launch_card(plugin_root):
    """The per-phase Continue is gone. A `claude --session-id` paste command in the
    master skill would send the user to an engine that no longer exists."""
    text = _skill_text(plugin_root)
    assert "--session-id" not in text, (
        "SKILL.md must not render a `claude --session-id` launch card: the external "
        "per-phase-session engine was removed, so a pasted phase session would "
        "claim a task nothing can complete"
    )


def test_skill_claims_surface_independence(plugin_root):
    """The whole point of the removal: a subagent runs wherever its parent runs, so
    the pipeline no longer stalls in the VS Code extension / desktop chat."""
    text = _skill_text(plugin_root).lower()
    assert "every surface" in text, (
        "SKILL.md must state that the pipeline advances on every surface"
    )


def test_skill_offers_no_mode_question(plugin_root):
    """single_session is the sole mode — Step 3 must not ask the user to pick one.

    `multi_session` may still be NAMED (Resume Support has to tell a user with a stale
    config what to fix), but it must never be offered as a choice.
    """
    text = _skill_text(plugin_root)
    assert "Change mode" not in text, (
        "Step 3 must not offer a 'Change mode' option — there is only one mode"
    )
    assert '--mode "{mode}"' not in text, (
        "Step 4 must not thread a user-selected mode into write-config"
    )
    assert "single_session" in text, "SKILL.md must name the sole mode"
    assert "multi_session (deprecated)" not in text, (
        "multi_session must not be presented as a (deprecated but selectable) option"
    )
    # Any mention of the removed mode must sit in a removal/migration context — never
    # as an option. Windowed, not line-based: the prose wraps.
    lowered = text.lower()
    i = lowered.find("multi_session")
    while i != -1:
        window = lowered[max(0, i - 300):i + 300]
        assert "remov" in window or "migrat" in window, (
            "multi_session mentioned outside a removal/migration context near: "
            f"{text[max(0, i - 80):i + 80]!r}"
        )
        i = lowered.find("multi_session", i + 1)


def test_skill_documents_the_stale_config_migration(plugin_root):
    """A user resuming a pre-removal run must be told what to do, in the skill."""
    text = _skill_text(plugin_root)
    assert "mode_unsupported" in text, (
        "Resume Support must handle the mode_unsupported action a stale config yields"
    )
    assert "migrations/multi-session-to-single-session.md" in text, (
        "Resume Support must point a stale config at the migration note"
    )


def test_skill_stays_within_runtime_prompt_budget(plugin_root):
    """Runtime-prompt files target <= 400 lines (constitution)."""
    n = len(_skill_text(plugin_root).splitlines())
    assert n <= 400, f"run SKILL.md is {n} lines (> 400 runtime-prompt budget)"
