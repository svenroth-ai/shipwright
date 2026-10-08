# Iterate Spec: runner-lease-and-agent-tool

- **Run ID:** iterate-2026-10-08-runner-lease-and-agent-tool
- **Type:** change
- **Complexity:** medium
- **Status:** built (awaiting review cascade)

## Goal
Make a campaign sub-iterate runner (a) record its unit's worktree reliably and (b) run its own
internal reviews, instead of recording them `not_run` and leaving the cascade to the orchestrator.

## Acceptance Criteria
- [x] AC1 (Part 1a): the runner brief's `check_unit_lease.py touch` passes `--attempt`/`--attempt-id`, so a claimed row accepts it and `loop_state.json` gets the unit's `worktree`; a failed touch is loud (`LEASE-TOUCH-FAILED`, one retry, `finalization.lease_touch: "failed"`), and `3f-bis`'s fallback to the shared worktree prints `LEASE-FALLBACK`.
- [x] AC2 (Part 1b): the loop env (`SHIPWRIGHT_LOOP_ID`, `SHIPWRIGHT_LOOP_UNIT_ID`) does not leak into `shared/tests` — reproduced first (15 failures in 5 files with the vars set, 0 without); the autouse fixture scrubs them.
- [x] AC3 (Part 1c): the runner brief says a unit's new CLI flag is absent from the plugin cache until its PR merges, so it runs its worktree's own copy of the script.
- [x] AC4 (Part 2): `sub-iterate-runner` lists the `Agent` tool and spawns `architecture-internal-reviewer`, `opus-plan-reviewer` (Step 3.5, medium+) and the `spec`→`code`→`doubt` cascade (Step 3.7) with `model=opus`, recording rows `completed`.
- [x] AC5: `3f-bis` stays the fallback — a runner whose spawn fails records `not_run --reason-code delegated-to-orchestrator` / `no-spawn-site`. 3f-bis is NOT skipped for a runner that did spawn: the runner's rows are self-attested (no verdict or reviewed-head binding), so the orchestrator's independent gate re-runs and `--force`-promotes (internal plan review + architecture review, high findings). Skipping is a follow-up that needs verdict + reviewed-head evidence.
- [x] AC6: `campaign-mode.md`, `iteration-reviews.md` (Campaign sub-iterate rows), `docs/`, the result schema and the tests that pinned "runner has no Agent tool" describe the new contract.

## Spec Impact
- **Classification:** none
- **NONE justification:** behaviour of the iterate skill's campaign runner changes, but FR-01.11's requirement text (depth-scaled change handling with enforced review record) is unchanged — this makes an existing guarantee hold in campaign units where the runner could not spawn reviewers. Affected FR: FR-01.11.

## Out of Scope
- Codex Light (no Agent tool by construction). Claude Code and Codextender only.
- Spawning the external review (`external_review.py`) from the runner — unchanged.
- Changing the orchestrator's 3f-bis shell beyond the LEASE-FALLBACK message.

## Design Notes
Spawn details live in the new `references/campaign-step-3-7-internal-reviews.md` (the runner brief and `campaign-mode.md` are at their pinned bloat ceilings 510 / 1708). Alternatives rejected: (1) write the worktree at claim time in `loop_claim.py` — code change with its own fencing semantics, the token fix is a one-flag doc fix; (2) skip the 3f-bis re-review when the runner already did — tried, then dropped: self-attested rows.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| runner `check_unit_lease.py touch` | `3f-bis` `jq` over `loop_state.json` `.units[].worktree` | JSON |

## Confidence Calibration
- **Boundaries touched:** loop_state.json lease fields; reviews.json record shape.
- **Empirical probes run:** `check_unit_lease.main` driven with the flags parsed out of the runner brief against a claimed row — token accepted & worktree written, token-less refused (test). `record_review_pass.py show … | jq` shape verified live (needs `PYTHONUTF8=1` on Windows). Loop-env leak reproduced then fixed (bisected: `LOOP_ID`, `LOOP_UNIT_ID` each sufficient, `SESSION_ID` not).
- **Test Completeness Ledger:** see F5 block; every behaviour tested.
- **Confidence-pattern check:** the 3f-bis shell is test-pinned prose (88 pinning tests pass); 3f-bis behaviour is unchanged apart from the LEASE-FALLBACK message.
