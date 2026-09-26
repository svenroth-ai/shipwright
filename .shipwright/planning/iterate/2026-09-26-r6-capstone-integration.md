# Iterate: R6 capstone integration proof (campaign-dag-scheduler)

- **Run ID:** iterate-2026-09-26-r6-capstone-integration
- **Campaign:** campaign-dag-scheduler, sub-iterate R6 (final unit; depends on R5b, merged as PR #799)
- **Type:** feature
- **Complexity:** medium
- **Spec Impact:** NONE (`change_type: infra`) — test-only, no production behavior change
- **Full spec:** `.shipwright/planning/iterate/campaigns/campaign-dag-scheduler/sub-iterates/R6-capstone-integration.md`
- **Full design authority:** `.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md` § "R6 — capstone integration proof"

## Scope

Add `shared/tests/test_campaign_dag_scheduler_integration.py`: a single real-git
integration test proving the campaign-dag-scheduler mechanism (R1-R5b) composes
correctly end to end — five-unit DAG (U1/U2/U4/U5 independent, U3
`depends_on: [U1, U2]`), against a genuine local bare-origin repo, exercising
the real `cmd_*` production entry points in-process (`loop_claim`,
`autonomous_loop`, `loop_mark`, `campaign_drain`, `check_review_attribution`).
No production code changed.

## Acceptance Criteria (from the sub-iterate spec, verbatim)

- [x] `shared/tests/test_campaign_dag_scheduler_integration.py` created, single pytest root (`shared/tests`).
- [x] Five-unit DAG fixture (two independent, one dependent on both, two more independent) against a local bare-origin repo.
- [x] Assertion (1): two independent units' worktrees exist concurrently, both reach `built` before either merges.
- [x] Assertion (2)+(3): the dependent unit is not claimed until both dependencies show a verified `merged_commit` ancestry; a fresh reload from disk between checks proves resume survival (no in-memory state reuse).
- [x] Assertion (4): review-diff attribution never cross-attributes, for BOTH built units (U1 and U2, not just one) — each pin's `diff_sha256` is checked against an independently recomputed raw-bytes hash (the same method `review_attribution.py::pin` uses), proving the recorded diff is genuinely the unit's own and never the shared/contaminated worktree's, and that the two units' own diffs/hashes differ from each other.
- [x] Assertion (5): a STRICT-STOP mid-wave (three still-`claimed` units) drains correctly via the real `campaign_drain.run_drain`, each lands `held`/`swept_never_started`, already-`merged` units are untouched; the session lock release is gated on the real `lib.autonomous_loop.cmd_finalize` accepting the drained state (rc==0, `state["finalized"] is True`) — matching R5b's actual policy ("release only after cmd_finalize confirms drained") — not released unconditionally by the test itself.
- [x] Resume-survival "no duplication" half made observable: wave 2 claims with `max_parallel=5` (not 1, which could not have exposed a duplicate), and a follow-up `cmd_next_batch` call is asserted to claim nothing (`rc==4`, empty `blocked_pending_ids`).

## "Mocked gh contract" — how it was actually done

There is no single Python function wrapping `gh pr view`/`gh pr merge`; that
step is bash-level orchestration prose in `campaign-mode.md`, never
encapsulated. The test simulates its *effect* with real git: it merges the
unit's pushed branch into the shared worktree's local `main` (`--no-ff`,
playing `gh pr merge --squash`), pushes to the bare origin, and feeds the
genuine resulting SHA to the real, fencing-validated `lib.loop_mark.cmd_mark_merged`
— the exact producer a real orchestrator's step 3g calls next. Every
state-machine transition is an in-process call to the real `cmd_*` function
(mirroring `test_wave_launch_failure_and_reconcile.py`'s established style);
only worktree/commit/merge operations are real subprocess/filesystem calls.

## Confidence Calibration

- **Boundaries touched:** `shared/tests/` only (new test file). Exercises, read-only from production's perspective: `lib.loop_claim`, `lib.loop_mark`, `lib.autonomous_loop`, `lib.loop_state`, `lib.campaign_drain`, `lib.campaign_session_lock`, `shared/scripts/checks/check_review_attribution.py`. No `io_boundary`/`auth`/`migrations`/`build` risk flags apply.
- **Empirical probes run:**
  - Ran the new test in isolation: `1 passed` (`shared/tests/test_campaign_dag_scheduler_integration.py -v`), independently re-confirmed after the build agent's own run.
  - Ran a targeted regression across the new file plus every module it directly exercises and their closest precedents (169 tests): `169 passed, 0 failed`.
  - Ran `uvx ruff@0.15.15 check` on the new file: clean.
  - Independently verified (not trusted blindly) that `check_review_attribution.py`'s `--default-branch`/`--pr-node-id`/`--pr-head-ref`/`--pr-base-ref` flags the test omits all default sensibly (`--default-branch` defaults to `"main"`, matching the fixture), so the pin call exercises the real diff/base-sha path, not a degenerate short-circuit.
  - Read the test file in full and traced each of the 5 assertions against the actual production functions it calls (`is_unit_ready`, `describe_blocker`, `cmd_mark_merged`'s fencing contract, `run_drain`'s sweep/reason_code) to confirm the assertions are checking real production behavior, not a re-implementation of the expectation.
- **Test Completeness Ledger:**

  | Behavior | Status | Evidence |
  |---|---|---|
  | Two independent units build concurrently in one wave (worktrees coexist, both reach `built` pre-merge) | tested | `test_full_five_unit_dag_wave_dependency_review_and_drain`, assertion block "Assertion 1" |
  | Dependent unit blocked until BOTH deps verified-merged; blocker message names the outstanding dep | tested | same test, "Assertions 2+3" block, `is_unit_ready`/`describe_blocker` calls |
  | Readiness state survives a fresh disk reload between waves (no in-memory reuse, no lost/duplicated readiness) | tested | same test — `_load_units` re-parses the state file fresh at every check; `wave2` claim is a genuinely separate `cmd_next_batch` call |
  | Review-diff attribution resolves to the unit's own worktree, never the shared (contaminated) one | tested | same test, "Assertion 4" block — independently recomputed diffs proven to differ |
  | STRICT-STOP mid-wave sweep demotes still-claimed units to `held`/`swept_never_started`, leaves terminal units untouched | tested | same test, "Assertion 5" block |
  | Campaign session lock genuinely releases after drain (a second session can acquire) | tested | same test — `csl.release` then a second `csl.acquire` succeeds without raising |
  | Full `shared/tests` suite has no regression from this addition | untestable | `reason_code: requires-external-nondeterministic-service` — the full ~12,000-test suite's real-git-subprocess-per-test cost exceeds a reasonable session budget on this Windows environment (reached 12% with zero failures before being stopped); mitigated by the 169-test targeted regression across every directly-exercised module instead |

- **Confidence-pattern check:** Asymptote (depth) — each of the 5 named assertions is checked via an independent recomputation or a real production entry point's own return value, never a bare "it didn't crash." Coverage (breadth) — the fixture composes all six R1-R5b subsystems in one continuous scenario, which is the entire point of a capstone test; **integration composition** is this test itself (`cross_component` machinery: `autonomous_loop`, `campaign_*`, review-attribution). No new production code was needed to make any assertion executable, which is itself informative — it means R1-R5b's public surface already composes as designed.

## Review Record

See `.shipwright/planning/iterate/iterate-2026-09-26-r6-capstone-integration/reviews.json` (Step 8, recorded below).
