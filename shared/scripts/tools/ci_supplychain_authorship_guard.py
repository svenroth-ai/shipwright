"""The operator-only guard for recording a CI supply-chain acknowledgement.

Split out of ``record_ci_supplychain_ack.py`` (trg-33d30377 / PR #718, then
the 300-line bloat gate) so the guard has one importable home other future
writers of this ack can also reach for, instead of only the one CLI.
"""

from __future__ import annotations

import os

#: Injected around an active autonomous-loop unit process — not only a
#: campaign sub-iterate runner (autonomous_loop's spawn of
#: `shipwright-iterate:sub-iterate-runner`): `shipwright-build`'s
#: `--autonomous` loop sets this SAME var around its own `section-builder`
#: spawn (`plugins/shipwright-build/skills/build/references/autonomous-loop.md`,
#: Step 3b) — it is one shared identifier for "an autonomous-loop-spawned
#: unit is running", not a campaign-specific one (doubt review,
#: trg-33d30377). Refusing either context is correct: no unattended loop
#: unit should self-author this ack, regardless of which loop spawned it.
#: Propagated to a spawned unit's Bash-tool subprocesses via
#: `capture_session_id.py`'s `CLAUDE_ENV_FILE` write. Absent for a
#: standalone iterate. Nothing unsets it once a unit returns — an operator
#: resolving an escalation must not carry it into their own terminal (see
#: `references/campaign-mode.md`'s operator note); this check cannot tell a
#: human's stray `export` apart from a real runner's.
CAMPAIGN_RUNNER_ENV_VAR = "SHIPWRIGHT_LOOP_UNIT_ID"


def refuse_if_campaign_runner_context() -> None:
    """Refuse outright while running inside an active autonomous-loop unit.

    No override flag: the contract this enforces (`references/campaign-mode.md`,
    Step 3.4) is unconditional — "the runner must never write that ack itself".
    Checked before anything else so the cheapest, most certain rejection fires
    first (mirrors the run-id guard in `record_ci_supplychain_ack.py`).
    """
    unit = os.environ.get(CAMPAIGN_RUNNER_ENV_VAR, "").strip()
    if unit:
        raise SystemExit(
            f"refusing to record a CI supply-chain acknowledgement: "
            f"{CAMPAIGN_RUNNER_ENV_VAR}={unit!r} is set, which means this process "
            "is running as an active autonomous-loop unit (a campaign "
            "sub-iterate runner, or a shipwright-build --autonomous "
            "section-builder — both share this var). Such a unit must "
            "never write its own ack (references/campaign-mode.md, Step "
            "3.4) — it certifies that a HUMAN reasoned about a "
            "trust-boundary change. Return status \"escalated\" instead; "
            "an operator records this acknowledgement from outside the "
            "active unit context (a fresh session, or the orchestrator's "
            "own shell once the unit has returned) and re-runs the unit. "
            "If you are an operator seeing this: you likely still have "
            f"{CAMPAIGN_RUNNER_ENV_VAR} exported in this shell (e.g. copied "
            "from campaign-mode.md Step 3b) — run "
            f"`unset {CAMPAIGN_RUNNER_ENV_VAR}` and retry."
        )
