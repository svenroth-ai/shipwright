"""Drift-protection for the interleaved-serial campaign loop
(iterate-2026-06-13-campaign-serial-default).

Replaces the old build-all-then-drain model (test_campaign_serial_drain.py).
Interleaved-serial: build ONE sub-iterate -> open PR -> wait CI green -> MERGE ->
build the NEXT from fresh origin/<default>. Only ever ONE campaign PR is open at
a time, so the multi-open-PR snapshot cascade that motivated the end-stage drain
cannot form — there is NO drain and NO regenerate-at-merge. The agent only
executes what the prose says, so the prose is the implementation (mirrors
test_f11_automerge_arm).
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
    assert "SHIPWRIGHT_ITERATE_AUTOMERGE=0" in text, (
        "campaign-mode.md must defer arming with SHIPWRIGHT_ITERATE_AUTOMERGE=0 so "
        "the orchestrator (not GitHub auto-merge) owns the per-PR merge."
    )


def test_campaign_loop_is_interleaved_serial() -> None:
    """The documented default is interleaved-serial with branch_strategy=serial."""
    text = _text()
    lowered = text.lower()
    assert "interleaved" in lowered and "serial" in lowered, (
        "campaign-mode.md must document the INTERLEAVED-SERIAL loop."
    )
    assert "--branch-strategy serial" in text, (
        "the loop init must pass `--branch-strategy serial` (the campaign default)."
    )


def test_merge_is_inside_the_loop_and_ci_green_gated() -> None:
    """The merge happens INSIDE the build loop (per sub-iterate, before Finalize),
    and only after CI is green — build -> CI-green -> merge -> next, not an
    end-stage drain. Pin the order: `gh pr checks --watch` precedes `gh pr merge`,
    and both precede the Finalize step."""
    text = _text()
    checks_pos = text.find("gh pr checks")
    merge_pos = text.find("gh pr merge")
    finalize_pos = text.find("**Finalize:**")
    assert checks_pos != -1, (
        "the loop must block on CI with `gh pr checks ... --watch` before merging."
    )
    assert "--watch" in text, "the CI wait must be a blocking `--watch`."
    assert merge_pos != -1, "the loop must merge each PR with `gh pr merge`."
    assert finalize_pos != -1, "campaign-mode.md must keep a Finalize step."
    assert checks_pos < merge_pos < finalize_pos, (
        "order must be CI-green (gh pr checks --watch) -> merge (gh pr merge) -> "
        "Finalize: the merge is per-iteration inside the loop, not an end-stage drain."
    )


def test_no_end_stage_drain() -> None:
    """The build-all-then-drain model is RETIRED: no 'Serial Merge Drain' stage and
    no per-PR ensure_current regenerate-at-merge in the campaign loop."""
    text = _text()
    assert "Serial Merge Drain" not in text, (
        "campaign-mode.md must NOT keep the end-stage 'Serial Merge Drain' — "
        "interleaved-serial merges each PR in turn inside the loop."
    )
    assert "ensure_current" not in text, (
        "the campaign loop must not run ensure_current regenerate-at-merge — with "
        "one PR open at a time the next sub-iterate composes on the prior merge."
    )


def test_serial_base_is_fresh_remote_default() -> None:
    """Each sub-iterate branches off the FRESH remote default ref (origin/<default>),
    so it can never inherit a stale local main."""
    text = _text()
    assert "origin/<default>" in text, (
        "campaign-mode.md must state the serial base is the fresh origin/<default> "
        "remote ref (not local main)."
    )
    assert "fresh" in text.lower(), "the freshness of the serial base must be explicit."


def test_strict_stop_on_non_delivered() -> None:
    """A non-delivered PR (CI fail / merge conflict / timeout) STRICT-STOPS the
    campaign — it does not proceed to the next sub-iterate."""
    text = _text()
    assert "STRICT-STOP" in text or "strict-stop" in text.lower(), (
        "campaign-mode.md must STRICT-STOP the campaign on a failed/non-delivered "
        "sub-iterate instead of building the next."
    )
