# iterate-2026-09-23-r5a-wave-build-flip — campaign-dag-scheduler R5a

Sub-iterate ADR: campaign-mode.md's flip from single-unit-at-a-time to
wave-based concurrent build. Referenced from the F3 decision-drop via
`--spec-ref`.

## External-Plan-Review-Findings

External plan review ran (`--mode iterate`, driver `claude`) against
`.shipwright/planning/iterate/campaigns/campaign-dag-scheduler/sub-iterates/R5a-wave-build-flip.md`.
Verdicts: openai=`revise`, glm=`approve` (contradiction check: not required —
within one step). Findings, each dispositioned:

| # | Source | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | R2 not named as an explicit merge prerequisite | **rejected-with-reason** — R2 is already merged to `origin/main` (campaign row order: R2 → R3 → R4 → R5a), and every sub-iterate branches off a freshly-fetched `origin/<default>` (loop step 2's `--branch-strategy serial`, enforced in code). The dependency is structurally satisfied at branch-off, not merely named in prose; no compatibility test is needed beyond the wrapper's own R2 tests, which already cover its output shape. |
| 2 | openai | high | No stated integrity/reconciliation contract for `result.json` (partial/stale/malformed) | **rejected-with-reason, largely pre-existing** — `autonomous_loop.cmd_record` already calls `lib.loop_state.enforce_record_fencing` TWICE (a pre-check and a re-check inside the same lock acquisition as the write), rejecting a mismatched or missing `attempt_id` (exit 1/5) before any state mutation, and validates `target_status` is a legal transition. This pre-dates R5a (R4's own external review already hardened it). R5a's own new tests (`test_wave_launch_failure_and_reconcile.py`) exercise the launch-failure and running-with-no-result paths through this exact fenced path. Atomic `result.json` publication by the runner (temp+rename) is the sub-iterate-runner's pre-existing Step 6 write, unchanged by this sub-iterate — tracked as a follow-up, not new scope here. |
| 3 | openai | medium | Release/fail transitions on wave-return not explicitly required to be fenced to the expected attempt owner | **rejected-with-reason** — `loop_claim.cmd_release` already requires `--attempt-id` and calls `validate_attempt_token`, rejecting a stale token (R4 work). 3e's release/demote calls in `campaign-mode.md` both pass `--attempt-id "{attempt_id from 3a}"`. |
| 4 | openai | medium | Sentinel lifecycle (set/clear) unspecified — could leak into unrelated later actions | **rejected-with-reason** — the sentinel is exported once, at loop step 1, for the lifetime of the WHOLE autonomous campaign session; the process performs no unrelated (non-campaign) actions after export, so there is nothing for it to leak into. Documented explicitly in campaign-mode.md's security note. |
| 5 | openai | medium | Test strategy mocks the Task/Agent barrier itself, so it can't catch an implementation that processes partial wave completions | **accepted, partially covered** — `test_campaign_wave_serialization_prose.py` is a content guard on the loop's OWN prose stating the barrier and non-goal explicitly (so a reader/session cannot rationalize overlap); a fully deterministic multi-Task harness is not buildable from a script (the Task/Agent tool has no test double in this repo) — logged as a documented gap in campaign-mode.md's own "Why interleaved-serial" section rather than silently claimed as covered. |
| 6 | glm | medium | Fencing token (`attempt_id`) provenance for the brief not pinned down | **rejected-with-reason** — already resolved: `attempt_id` is explicitly listed in the sub-iterate-runner Input block and Step 1.0.5, minted once by `loop_claim.cmd_next_batch` at 3a and threaded unchanged through 3b/3c's brief into the runner's own claim-promotion call — the SAME token the orchestrator claimed with, never re-derived. |
| 7 | glm | medium | Migration off `SHIPWRIGHT_LOOP_UNIT_ID` should fail loud, not fall back silently, in case the consumer enumeration missed a path | **rejected-with-reason** — the actual migration does not introduce a new `unit_id` parameter with a silent-fallback default; `resolve_wave_safe_unit_value` degrades the sentinel to `""` and the existing multi-tier `resolve_run_id`/handoff resolution falls through to its LOWER tiers exactly as if `SHIPWRIGHT_LOOP_UNIT_ID` had never been set (pre-campaign, standalone-iterate behaviour) — it can never resolve to the literal sentinel string, so the collision GLM describes (all units resolving to one shared identity) cannot occur. Covered by `test_campaign_wave.py`. |
| 8 | glm | medium | A wave where every unit launch-fails produces the identical next wave — no no-progress circuit breaker | **accepted, deferred** — a real gap; `loop_claim.cmd_next_batch` has no such breaker today. Out of R5a's stated scope (state-machine breaker logic is new production surface, not a prose flip) and non-trivial to land safely under `autonomous_loop.py`'s zero-headroom line pin. Filed as a follow-up triage item rather than rushed into this diff. |
| 9 | glm | low | Explicit inner-loop restructuring of 3f-bis..3i over the wave's units not spelled out | **accepted-and-fixed** — the wrapping paragraph before 3f-bis explicitly states the per-unit, fixed-order drain and that 3f-bis/3g/3h bodies are otherwise unchanged (R5b's job). |
| 10 | glm | low | Dangling worktrees/branches for failed units — no named cleanup owner | **rejected-with-reason** — `loop_claim.cmd_release`'s own docstring names `_cleanup_unit_worktree` as a best-effort, non-blocking step run after the logical release; this is pre-existing R2/R4 behaviour, not new to R5a. |
| 11 | glm | low | A mid-wave crash strands up to N `running` units — confirm R4's stale-claim recovery is N-runner-safe | **accepted, partially covered** — `test_wave_launch_failure_and_reconcile.py` includes a multi-unit demote-to-`failed` case; a dedicated liveness-sweep-under-N-concurrent-runners test is left to R5b/R6, which own the merge-lane's longer-running failure modes. |
| 12 | glm | low | Demote-to-failed command name/location given the 436-line pin | **rejected-with-reason** — there is no separate "mark-failed" command; 3e's demotion reuses the SAME `autonomous_loop.py record --result '{"status":"failed",...}'` fenced path a real result uses (stated explicitly in campaign-mode.md 3e). No new surface added to `autonomous_loop.py`. |
| 13 | glm | low | The wave-not-spawned-before-drain-clears property lives in prose; a test should target the Python precondition, not the markdown | **accepted, partially covered** — no single Python function owns this precondition today (the loop is agent-driven prose, not a Python state machine that enforces ordering itself); `test_campaign_wave_serialization_prose.py` is the closest available guard. Logged as a known limitation of testing an agent-prose orchestrator, not fixed further here. |

Recorded via `record_review_pass.py --review-type plan --status completed
--from external-review-json`, `--marker-status completed`, provider `openrouter`.
`plan_internal` recorded `not_run` (campaign sub-iterates have no internal
plan-review arm yet — documented gap, trg-71d7a4fa/trg-d6cc3d3d).

## External-Code-Review-Findings

External code review ran (`--mode code`, driver `claude`, full diff vs.
`origin/main`). Verdicts: openai=`revise`, glm=`revise` (agree; no
contradiction). Both legs independently found the same real spec deviation
(attempt-scoped result path) — high confidence it was genuine, not noise.

| # | Source | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | Step 1.0.5 (`sub-iterate-runner.md`) is unconditional even though `state_path`/`unit_id`/`attempt_id` are documented as absent on a standalone-shaped dispatch (this very sub-iterate's own dispatch, predating its own flip) | **accepted-and-fixed** — Step 1.0.5 now explicitly skips when those three fields are absent, mirroring the existing "Step-boundary liveness touches" conditional. Bloat-exception addendum filed (512→524) for the extra prose. |
| 2 | openai + glm (both legs) | high / medium | The canonical result path omits the `a{attempt}` component the spec's own acceptance criteria name explicitly (`runs/{loop_id}/{unit_id}/a{attempt}/result.json`); runner Step 6, campaign-mode.md 3e, and the reconciliation test all used the attempt-less path | **accepted-and-fixed** — Step 6, 3e's read path, and `test_wave_launch_failure_and_reconcile.py`'s illustrative path all updated to the attempt-scoped shape. Verified this needed NO change to `autonomous_loop.cmd_record`/`runs_dir_for` — those are a separate, unit-scoped (not attempt-scoped) internal bookkeeping path or the fenced-record write, not the runner's own raw `result.json` write the orchestrator reads back at 3e. |
| 3 | openai | high | The synthetic `running`-no-result record at 3e returns the SAME exit `3` a real failure does at 3f, but 3e's prose never said to STRICT-STOP the wave on it the way 3f explicitly does | **accepted-and-fixed** — one explicit sentence added to 3e: this call's exit code follows 3f's own STRICT-STOP rule. |
| 4 | glm | medium | `campaign_wave.py`'s `is_wave_sentinel` docstring claimed `id_charset_ok`'s charset "does not even permit an underscore" — factually wrong, the charset (`._-`) includes underscore mid-string | **accepted-and-fixed** — docstring corrected to the real reason (leading/trailing-separator rejection, not an underscore ban); `id_charset_ok(WAVE_UNIT_ID_SENTINEL) is False` is now asserted directly in `test_campaign_wave.py`. The underlying safety property (no real id can equal the sentinel) was never wrong, only its stated reason. |
| 5 | openai | medium | Migrated consumers derive an identifier via `resolve_run_id(project_root, ...)` rather than a brief-provided `unit_id` argument, and can fall back to `loop_id` alone if the per-unit pointer is missing, without failing loud | **rejected-with-reason** — same disposition as the plan-review's equivalent finding (#7 above): each unit runs in its OWN per-unit worktree post-flip, so `resolve_run_id` is called with a per-unit `project_root` and its higher tiers (the run pointer written into that worktree) resolve correctly; the shared-`loop_id`-only tier is the SAME degradation that already existed pre-campaign for a genuinely standalone run with no pointer, not a new hazard the sentinel introduces. Hard-failing here would turn a graceful degradation this codebase already relies on elsewhere into a new STOP condition, which is out of this sub-iterate's scope to introduce codebase-wide. |
| 6 | openai | medium | `test_derived_snapshots_wave_concurrency.py`'s concurrency test ran the two `restore_derived_to_head` calls SEQUENTIALLY in one process and covered only 2 of the 10 restorable paths | **accepted-and-fixed** — new `test_truly_concurrent_restores_across_all_ten_restorable_paths_never_cross_contaminate` uses a `threading.Barrier` to force two real overlapping `git` subprocess calls (one per worktree) and covers every path in `RESTORABLE_SNAPSHOTS`. |

## External-Code-Review-Findings — round 2 (re-run against the round-1 fixes)

Verdicts: openai=`revise`, glm=`revise` (agree). Both legs explicitly
confirmed round 1's fixes landed ("Positive verification" — glm). Remaining
findings:

| # | Source | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | Step 1.0 (the isolation check ITSELF, distinct from 1.0.5) was still unconditional — the SAME class of bug round 1 fixed for 1.0.5 alone | **accepted-and-fixed** — item 0 now branches the same way: `--campaign-slug "{campaign_slug}"` when `unit_id` is absent, the composite per-unit guard otherwise. All three steps (0, 0.5, 6) now check the SAME canonical field (`unit_id`), closing glm's separate low finding about the two guards using different field subsets. |
| 2 | openai + glm (both, high) | high | Traced fully: the sentinel's fallback (`resolve_run_id`) has its OWN tier-1 pointer keyed by `session_id` — every unit in a wave shares the same `SHIPWRIGHT_SESSION_ID`, so N concurrent `setup_unit_worktree.py` calls write to the SAME `<main_root>/.shipwright/iterate_active/<session_id>.json`, last-writer-wins. Worse than either review's original guess (a tier-3 `loop_id`-alone degradation) — this is a tier-1 collision. | **accepted-and-fixed** — new `campaign_wave.per_unit_worktree_identity(project_root)` returns the per-unit worktree's OWN directory basename (already required-unique by `check_worktree_location.py`'s own guard) and is now consulted BEFORE `resolve_run_id` in both `write_wave_aware_handoff` and `_run_id.py`'s tier-3 — the session-keyed pointer is never reached from a per-unit worktree. New tests reproduce the exact collision scenario (`resolve_run_id` mocked to return the SAME colliding value for two units) and prove the two outputs still differ. |
| 3 | openai | medium | 3c's per-unit setup/guard failure STRICT-STOPs without releasing units already claimed earlier in the SAME wave by 3a | **accepted-and-fixed** — 3c now releases every already-claimed unit (its own `attempt_id` from 3a) before stopping. |
| 4 | glm | medium | No-progress circuit breaker still entirely unmentioned in the shipped prose (round 1 deferred the STATE-MACHINE breaker but left no operational warning at all) | **accepted-and-fixed, partially** — one sentence added at 3i: a wave with zero recorded results must STOP and report, not silently re-claim the identical ready set. The state-machine-level breaker itself remains deferred (unchanged disposition from the plan review). |
| 5 | glm | medium | The wave-serialization AC still has no Python-level enforcement, only the prose guard | **rejected-with-reason, unchanged** — same disposition as plan-review finding #13 and round-1 code-review finding #5: no test double exists for the Task/Agent barrier in this repo; documented as a known limitation, not silently claimed as covered. |
| 6 | glm | medium | The spec literally says "read the brief-provided `unit_id` directly" — the implementation still does not thread that literal field, even after the fix | **rejected-with-reason, strengthened** — the safety property the AC exists FOR (no cross-unit collision) is now materially stronger than a literal `unit_id` thread would be on its own, since `per_unit_worktree_identity` requires no plumbing change to session/lock/lease call sites that a literal `unit_id`-threading would have touched. Noted in F3a reflection as a deliberate interpretation, not a literal-text match. |
| 7 | glm | low | Named test only covers `RESTORABLE_SNAPSHOTS` (10), not "twelve" | **rejected-with-reason, unchanged** — `TEST_RESULTS`/`SESSION_HANDOFF` are excluded from `RESTORABLE_SNAPSHOTS` by design (run-evidence paths a restore must never touch); the test docstring already names this. |

Recorded via `record_review_pass.py --review-type external_code --status
completed --from external-review-json`, `--marker-status completed`,
provider `openrouter`. `spec`/`code`/`doubt` recorded `not_run`, delegated to
the orchestrator's 3f-bis cascade (ADR-029, campaign mode only — the runner
has no `Agent` tool).

## Confidence Calibration

Fires: effective complexity medium + `touches_io_boundary`-adjacent surface
(the result.json / per-unit-identity boundaries this sub-iterate's own
external review round 2 surfaced).

**Boundary 1 — per-unit identity (`campaign_wave.per_unit_worktree_identity`).**
Producer: `setup_unit_worktree.py` / `composite_worktree_name` (the worktree
directory itself). Consumer: `write_wave_aware_handoff` +
`_run_id.py` tier-3. Probes run (real `Path` objects, no mocks): (1) a real
Windows absolute path with backslashes, (2) a path carrying the `-a{attempt}`
retry suffix, (3) a path with a trailing `.` segment, (4) a CWD-relative path
(the shape the runner actually sees after its own `cd`). All four: no
findings — two consecutive clean probes past the first reached the asymptote.

**Boundary 2 — attempt-scoped `result.json` round trip.** Producer: the
runner's own Step 6 write. Consumer: 3e's read. Probes run (real file writes
+ reads, no mocks): (1) producer-writes -> consumer-reads at the identical
attempt-scoped path, verifying the exact JSON round-trips byte-for-byte; (2)
a superseded prior attempt (`a0`) and the current attempt (`a1`) never alias
— writing `a1`'s result leaves `a0`'s completely untouched. Both: no
findings.

Edge cases not probed (acceptable): actual concurrent (multi-process) writes
to two DIFFERENT units' `result.json` paths — already covered by the
`threading.Barrier` test for `restore_derived_to_head`, and `result.json`
writes are per-unit-directory-isolated by construction (never a shared file),
so the concurrency argument transfers without a separate probe.

Asymptote reached both boundaries — no repeat run needed.
