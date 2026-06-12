"""Drift-protection for the F11 Delivery-Watch + the F2 content-lint-before-push
rule (iterate-2026-06-12-delivery-watch; memory `feedback_no_shoot_and_forget`).

The 2026-06-12 #213 miss: the iterate was reported "done" the moment auto-merge
was armed, while a Required Check was RED (an over-budget architecture.md entry
failed the iterate-plugin agent-doc budget gate, which is NOT in the shared/tests
F0 run). Two prose rules close it; the agent only executes what the prose says, so
these pin that the prose says it (mirrors test_f11_automerge_arm).
"""

from __future__ import annotations

from pathlib import Path

_ITERATE = Path(__file__).resolve().parent.parent / "skills" / "iterate"
_F11 = _ITERATE / "references" / "F11.md"
_F2 = _ITERATE / "references" / "F2.md"
_SKILL = _ITERATE / "SKILL.md"


def test_f11_runs_delivery_watch_after_the_arm() -> None:
    """F11 must run `watch_pr_delivery.py` AFTER arming auto-merge — the run is
    not done until the PR is delivered, not when it is armed."""
    text = _F11.read_text(encoding="utf-8")
    assert "watch_pr_delivery.py" in text, (
        "F11.md must run watch_pr_delivery.py to confirm the PR actually merges "
        "(no shoot-and-forget)."
    )
    arm_pos = text.index("--auto --squash --delete-branch")
    watch_pos = text.index("watch_pr_delivery.py")
    assert arm_pos < watch_pos, "the delivery watch must come AFTER the auto-merge arm."


def test_f11_defines_delivered_as_merged_and_kills_shoot_and_forget() -> None:
    """The contract: delivered = MERGED (+ green); arming alone is NOT done."""
    text = _F11.read_text(encoding="utf-8")
    low = text.lower()
    assert "shoot and forget" in low, (
        "F11.md must name the 'shoot and forget' anti-pattern it forbids."
    )
    assert "delivered" in low and "merged" in low, (
        "F11.md must define delivery as MERGED, not armed."
    )
    # Fail CLOSED: EVERY non-merged outcome of the watch (checks_failed / closed /
    # timeout / gh-error) must STOP the run, so a pending/errored watch can never
    # be treated as "done" (external-review fix).
    assert "NOT DELIVERED" in text
    # F11.md has an earlier `case "$head_branch" in … esac` (the arm) — anchor the
    # esac to AFTER `case "$?" in` so we slice the delivery-watch block, not the arm.
    cstart = text.index('case "$?" in')
    block = text[cstart:text.index("esac", cstart)]
    for case in ("2)", "3)", "4)", "*)"):
        seg = block[block.index(case):]
        seg = seg[:seg.index(";;")]
        assert "exit 1" in seg, (
            f"F11 delivery-watch branch `{case}` must fail closed (exit 1); only `0)` "
            "(merged + green) may proceed."
        )
    # And the success branch must NOT exit 1 (it proceeds to "delivered").
    zero = block[block.index("0)"):]
    zero = zero[:zero.index(";;")]
    assert "exit 1" not in zero


def test_f2_requires_running_the_agent_doc_budget_lint_before_push() -> None:
    """F2 must tell the agent to run the iterate-plugin agent-doc budget lint
    locally before push — it is NOT in the shared/tests F0 run (the #213 gap)."""
    text = _F2.read_text(encoding="utf-8")
    assert "test_agent_doc_entry_rules.py" in text
    low = text.lower()
    assert "before push" in low or "before you push" in low, (
        "F2.md must require running the budget lint BEFORE push."
    )
    assert "shared/tests" in text and "f0" in low, (
        "F2.md must explain WHY (the gate is outside the shared/tests F0 run)."
    )


def test_skill_f11_index_advertises_delivery_watch() -> None:
    skill = _SKILL.read_text(encoding="utf-8")
    rows = [ln for ln in skill.splitlines() if ln.startswith("| F11 ")]
    assert rows, "no `| F11 |` index row in SKILL.md"
    assert "watch_pr_delivery" in rows[0] or "deliver" in rows[0].lower(), (
        "SKILL.md F11 index row must advertise the delivery watch."
    )
