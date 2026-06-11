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
