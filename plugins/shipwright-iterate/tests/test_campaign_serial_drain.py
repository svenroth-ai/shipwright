"""Drift-protection for the campaign serial integrate_main merge drain
(iterate-2026-06-12-automerge-serial-integrate — Auto-merge churn fix, Option A).

GitHub auto-merge does a server-side 3-way merge and NEVER runs the
regenerate-at-merge resolver. Arming `gh pr merge --auto` on every sub-iterate PR
of an `--autonomous` campaign simultaneously makes the still-open PRs cascade
DIRTY (snapshot conflict) or merge stale (Group-E staleness) as the others merge.

Option A: under `--autonomous`, sub-iterate F11 DEFERS the arm
(`SHIPWRIGHT_ITERATE_AUTOMERGE=0`) and the orchestrator drains the PRs SERIALLY —
for each in turn it runs `integrate_main` (`--ensure-current`) to bring the
branch current with the now-advanced origin/main (regenerating the snapshots),
then merges. This is content drift-protection: the agent only executes what the
prose says, so the prose is the implementation (mirrors test_f11_automerge_arm).
"""

from __future__ import annotations

from pathlib import Path

CAMPAIGN_MODE = (
    Path(__file__).resolve().parent.parent
    / "skills" / "iterate" / "references" / "campaign-mode.md"
)


def _text() -> str:
    return CAMPAIGN_MODE.read_text(encoding="utf-8")


def test_campaign_mode_reference_exists() -> None:
    assert CAMPAIGN_MODE.is_file(), f"campaign-mode reference missing at {CAMPAIGN_MODE}"


def test_campaign_defers_arm_via_env() -> None:
    """Sub-iterate runners under an autonomous campaign must defer the auto-merge
    arm via `SHIPWRIGHT_ITERATE_AUTOMERGE=0` so the orchestrator owns the merge."""
    text = _text()
    assert "SHIPWRIGHT_ITERATE_AUTOMERGE" in text, (
        "campaign-mode.md must set SHIPWRIGHT_ITERATE_AUTOMERGE=0 for sub-iterate "
        "runners so their F11 defers arming and the campaign drains serially."
    )
    assert "SHIPWRIGHT_ITERATE_AUTOMERGE=0" in text, (
        "campaign-mode.md must explicitly defer arming with "
        "SHIPWRIGHT_ITERATE_AUTOMERGE=0."
    )


def test_campaign_drains_serially_via_ensure_current() -> None:
    """The drain must reconcile each branch through ensure_current.py (host-agnostic
    regenerate-at-merge over integrate_main), NOT rely on GitHub's server-side
    auto-merge — and it must spell out the per-PR sequence (refresh → push → merge
    → wait), one PR at a time. Substring presence is not enough; pin the steps."""
    text = _text()
    lowered = text.lower()
    assert "ensure_current.py" in text, (
        "campaign-mode.md serial drain must run ensure_current.py to bring each "
        "branch current (regenerating snapshots) before merging — server-side "
        "auto-merge cannot regenerate them."
    )
    assert "serial" in lowered and "drain" in lowered, (
        "campaign-mode.md must document the SERIAL merge DRAIN (one PR at a time)."
    )
    # The per-PR sequence the orchestrator runs for each PR in turn.
    drain_pos = text.index("ensure_current.py")
    drain = text[drain_pos:]
    assert "git -C" in drain and "push" in drain, (
        "the drain must push the integrate commits before merging the PR."
    )
    assert "gh pr merge" in drain, "the drain must merge each PR (gh pr merge)."
    assert "poll" in drain.lower() or "wait" in drain.lower(), (
        "the drain must WAIT for each PR to merge before the next (so the next "
        "branch integrates an origin/main that already contains the prior PR)."
    )
