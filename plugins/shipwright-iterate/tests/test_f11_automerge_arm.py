"""Drift-protection for the F11 auto-merge arm (B4.5 Phase 3, trg-bdc160e2).

After `gh pr create`, F11 must arm GitHub-native auto-merge so an iterate
PR squash-merges itself once the Required Checks pass — but ONLY for
`iterate/*` branches (a manual human PR must never self-arm) and ONLY
fail-soft (if "Allow auto-merge" / branch protection is off in repo
settings, `gh pr merge --auto` errors — that must warn and leave the PR
open, never fail the whole iterate run).

These assertions pin the four properties that make the arm safe:

1. The arm call exists with the exact flags `--auto --squash --delete-branch`.
2. It is guarded to `iterate/*` branches (the `case … iterate/*)` glob).
3. It is fail-soft (a `||` fallback, and NOT `|| exit`/hard failure).
4. The Kern SKILL.md F11 one-liner advertises the arm so the index does
   not drift from the reference.

It is content drift-protection, mirroring `test_skill_step_6_rules_present.py`
and `test_skill_references_link.py` — the agent only executes what the
prose says, so the prose is the implementation.
"""

from __future__ import annotations

import re
from pathlib import Path

ITERATE_SKILL = (
    Path(__file__).resolve().parent.parent / "skills" / "iterate"
)
F11_PATH = ITERATE_SKILL / "references" / "F11.md"
SKILL_PATH = ITERATE_SKILL / "SKILL.md"


def _f11_text() -> str:
    return F11_PATH.read_text(encoding="utf-8")


def _join_line_continuations(text: str) -> str:
    """Collapse shell `\\`-newline continuations so a multi-line command
    is matched as one logical line."""
    return re.sub(r"\\\s*\n\s*", " ", text)


def test_f11_reference_exists() -> None:
    assert F11_PATH.is_file(), f"F11 reference missing at {F11_PATH}"


def test_arm_call_present_with_exact_flags() -> None:
    """The auto-merge arm must call `gh pr merge … --auto --squash
    --delete-branch` (the spec's exact flag set)."""
    text = _join_line_continuations(_f11_text())
    assert re.search(
        r"gh pr merge\s+\S+\s+--auto\s+--squash\s+--delete-branch", text
    ), (
        "F11.md must arm auto-merge with "
        "`gh pr merge \"$pr_url\" --auto --squash --delete-branch` "
        "after `gh pr create`."
    )


def test_arm_is_guarded_to_iterate_branches() -> None:
    """The arm must be gated on an `iterate/*` branch check so a manual
    human PR never self-arms."""
    text = _f11_text()
    assert "iterate/*" in text, (
        "F11.md auto-merge arm must be guarded to `iterate/*` branches "
        "(e.g. a `case \"$branch\" in iterate/*)` glob) — a manual PR "
        "must never self-arm."
    )


def test_arm_is_fail_soft_not_hard_exit() -> None:
    """`gh pr merge --auto` must be fail-soft: a `||` fallback that warns
    and leaves the PR open, never `|| exit` / a hard failure that would
    break F11 for every future iterate when the repo setting is off."""
    text = _join_line_continuations(_f11_text())
    arm_lines = [
        ln for ln in text.splitlines()
        if "--auto --squash --delete-branch" in ln
    ]
    assert arm_lines, "no auto-merge arm line found to check fail-soft"
    for ln in arm_lines:
        assert "||" in ln, (
            "auto-merge arm must have a `||` fail-soft fallback: " + ln
        )
        assert not re.search(r"\|\|\s*exit\b", ln), (
            "auto-merge arm must NOT hard-exit on failure (`|| exit`): " + ln
        )


def test_existing_gates_preserved() -> None:
    """Regression: the patch must not drop F11's leak-guard or the
    deterministic finalization verifier."""
    text = _f11_text()
    assert "check_iterate_isolation.py" in text, "F11 lost its leak-guard"
    assert "verify_iterate_finalization.py" in text, (
        "F11 lost its deterministic finalization verifier"
    )


def test_skill_index_line_advertises_arm() -> None:
    """The Kern SKILL.md F11 one-liner must mention the auto-merge arm so
    the index does not drift from the reference."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    f11_rows = [
        ln for ln in skill.splitlines()
        if ln.startswith("| F11 ")
    ]
    assert f11_rows, "no `| F11 |` index row found in Kern SKILL.md"
    row = f11_rows[0]
    assert "--auto" in row and "iterate/" in row, (
        "Kern SKILL.md F11 index row must advertise the `--auto` arm and "
        "its `iterate/`-only scope: " + row
    )


# --- Refresh-if-behind guard + campaign-defer (Option A, Auto-merge churn fix,
#     iterate-2026-06-12-automerge-serial-integrate) ------------------------------
# GitHub auto-merge does a server-side 3-way merge and NEVER runs the
# regenerate-at-merge resolver, so a branch that fell behind origin/<default>
# would merge stale (Group-E staleness) or stall DIRTY on the regenerated
# snapshots. F11 must (1) bring the branch current via `integrate_main
# --ensure-current` BEFORE arming, and (2) honor a campaign-defer env var so an
# `--autonomous` campaign merges each PR in turn (interleaved-serial) instead of
# arming every PR at once.


def test_f11_has_refresh_if_behind_guard() -> None:
    """F11 must run the `ensure_current.py` refresh BEFORE push / PR-create / arm,
    so the PR arms from a current, already-regenerated tree (server-side merge
    cannot regenerate the derived snapshots), AND it must be fail-closed: a
    non-churn/source conflict STOPs the run (hard safety gate)."""
    text = _f11_text()
    assert "ensure_current.py" in text, (
        "F11.md must invoke ensure_current.py to refresh a behind branch before "
        "arming auto-merge (server-side merge cannot regenerate snapshots)."
    )
    guard_pos = text.index("ensure_current.py")
    push_pos = text.index("push -u origin")
    create_pos = text.index("gh pr create")
    arm_pos = text.index("--auto --squash --delete-branch")
    assert guard_pos < push_pos < create_pos < arm_pos, (
        "the ensure_current.py refresh must run BEFORE the push, the PR create, "
        "and the auto-merge arm (so the branch is current when it ships/arms)."
    )
    # Fail-closed: a non-zero exit between the guard and the push must STOP.
    guard_block = text[guard_pos:push_pos]
    assert "exit 1" in guard_block and "STOP" in guard_block, (
        "the ensure_current guard must STOP (exit 1) on a non-churn/source "
        "conflict — the same hard safety gate as the resolver."
    )


def test_f11_arm_respects_campaign_defer() -> None:
    """The arm must be gated on a CONCRETE `SHIPWRIGHT_ITERATE_AUTOMERGE` shell
    check that wraps the `gh pr merge --auto` command, so an autonomous campaign
    can defer arming (`=0`) and let the orchestrator merge each PR in turn.
    Substring presence is not enough — pin the exact condition and that it
    precedes the arm."""
    text = _f11_text()
    assert '"${SHIPWRIGHT_ITERATE_AUTOMERGE:-1}" = "0"' in text, (
        "F11.md must gate the arm on an explicit "
        '`if [ "${SHIPWRIGHT_ITERATE_AUTOMERGE:-1}" = "0" ]` check (default ON=1 '
        "so single iterates are unchanged)."
    )
    gate_pos = text.index("SHIPWRIGHT_ITERATE_AUTOMERGE:-1")
    arm_pos = text.index("--auto --squash --delete-branch")
    assert gate_pos < arm_pos, (
        "the campaign-defer gate must WRAP the arm (appear before it) so =0 skips it."
    )
    assert "DEFERRED" in text, (
        "the deferred (=0) branch must NOT arm — it echoes a DEFERRED notice."
    )
