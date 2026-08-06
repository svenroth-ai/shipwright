"""Group E's suggested remedy must be one an operator can actually run.

iterate-2026-08-05-adopt-derived-evidence-rollout, AC-6.

Group E compares the on-disk document against the last snapshot COMMIT. `--fix`
rewrites the working tree, which clears the case the group was built for — a
hand-edit, where re-rendering restores the snapshot's content — but it cannot
clear a snapshot that is genuinely *behind*: re-rendering moves on-disk further
from it and the next audit reports the same finding. Only a new snapshot commit
clears that.

A separate module from `test_audit_group_e.py` because that file is at its
300-line cap; the subject is different too — that one covers snapshot semantics
and `--fix` wiring, this one covers what the finding TELLS somebody to do.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_e  # noqa: E402

SKILL_MD = PLUGIN_ROOT / "skills" / "compliance" / "SKILL.md"


def test_suggestion_names_a_path_that_can_actually_clear_the_finding() -> None:
    cmd = group_e._suggest("change_history")
    assert "--fix" in cmd, "the hand-edit case is still the common one"
    assert "--refresh-pr" in cmd, (
        "naming only --fix sends an operator round a loop it cannot exit: it "
        "rewrites the worktree, and the finding compares against the COMMIT"
    )
    assert "\n" not in cmd, (
        "audit_report renders this inside ONE inline code span, so a newline "
        "breaks the finding's markdown"
    )


def test_suggestion_names_only_flags_the_skill_actually_accepts() -> None:
    """Every flag in the remedy must appear in the skill's accepted-flag list.

    `--restore` is a flag of the internal `refresh_compliance_docs.py`, and Step
    2c runs it itself as the first line of the `--refresh-pr` procedure. Naming
    it in the finding sent the operator to type `/shipwright-compliance
    --restore`, which the skill does not accept — recreating the exact circle
    this remedy exists to break (Stage-2 code review).

    Checked against the SKILL as the source of truth rather than a hardcoded
    list, so a future flag rename cannot leave this passing on a stale copy.
    """
    cmd = group_e._suggest("change_history")
    skill = SKILL_MD.read_text(encoding="utf-8")

    flags = {tok.strip("`.,;") for tok in cmd.split() if tok.startswith("--")}
    assert flags, "the remedy names no command at all"
    for flag in flags:
        assert f"`{flag}`" in skill, (
            f"{flag} is not among the flags /shipwright-compliance accepts "
            f"(SKILL.md Step 1), so the remedy tells the operator to type "
            f"something that does not exist. Remedy was: {cmd!r}"
        )
