# Self-review — iterate-2026-07-27-phase-gate-override-evidence

The 7-point checklist (`references/iteration-reviews.md`).

## 1. Does it do what the spec said?

Both items close acceptance criteria that already existed on FR-01.01. Mapped:

| AC | Where it is satisfied | Where it is pinned |
|---|---|---|
| AC1 gate runs under force | `step_planning.py` — `if not is_standalone:` (was `if not force and not is_standalone:`) | `test_force_still_runs_the_phase_gate` |
| AC2 override recorded with what + why | `validation_record.record_validation_override` | `test_a_waved_through_completion_is_recorded_with_what_and_why` |
| AC3 passed ≠ waved through | no record on a clean unforced completion; `waived`/`gate_result` split | `test_a_clean_completion_records_no_override`, `test_force_over_a_clean_gate_records_a_pass_not_a_waiver` |
| AC4 reason mandatory | `normalise_override_reason` (library) + `parser.error` (CLI) | 4 parametrised lib cases + 2 CLI cases |
| AC5 pause rule unchanged | the `ask_issues and not force` branch is the old branch | `test_ask_issues_without_force_still_pause_the_run` |
| AC6 standalone unchanged | `if not is_standalone` still guards the whole gate | `test_standalone_skips_the_gate_and_records_nothing` |
| AC7 finished phases rendered | `render_pipeline_phases` tally + table | `test_finished_phases_are_named_and_tallied` |
| AC8 interrupted ≠ finished | `_finished_verdict` + the prose line | `test_a_phase_that_merely_started_does_not_count_as_finished` |
| AC9 dispatch pointer rendered | `_dispatch_lines` | `test_the_dispatch_pointer_is_rendered` |
| AC10 no phase_tasks → nothing | early `return []` | `test_a_config_without_phase_tasks_renders_nothing` |

## 2. Anything beyond the spec? (YAGNI)

Three additions beyond the literal brief, each traceable to a review finding, none
speculative:

- `[gate-error]` crash handling — plan-review **G1**. Not gold-plating: making the gate
  run under force *removed* the escape hatch a broken validator used to have.
- `validation_overrides_dropped` counter — plan-review **O6**.
- The path drift-guard integration test — plan-review **G3**.

Nothing else. No new CLI subcommands, no config knobs, no changes to
`single-session-apply` (out of scope by the brief and by the fact that the v2 path has
no `--force`).

## 3. Tests: do they falsify?

Verified empirically, not assumed. Reverting `step_planning.py` to the pre-change
behaviour turns **14 of 23** item-1 tests red; unwiring `render_pipeline_phases` turns
the item-2 end-to-end test red. The 9 item-1 tests that stay green are the ones pinning
*unchanged* behaviour (the pause rule, standalone, the CLI arg refusal, the retention
unit) — which is correct, they are regression guards, not new-behaviour proofs.

## 4. Error handling

- Broken validator → caught, surfaced as an ask-level issue, fail-closed unforced.
- Blank/whitespace reason → `ValueError` **before** the gate runs or anything is
  written; a malformed call cannot half-complete a phase.
- Missing / partial / non-object loop state → pointer lines omitted, table still
  renders. Never raises.
- Non-mapping `phase_tasks` rows, `phase_tasks` not a list, `run_config` `None` →
  all handled, all tested.

## 5. Concurrency / locking

The gate stays **outside** `run_config_lock` (it is read-only and slow — the audit
WP2/F11 property). Only `record_validation_override` runs inside, against the
reload-fresh config in the existing critical section. No new lock, no new lock-hold,
no lock held across the compliance subprocess. `test_update_step_complete_does_not_clobber_concurrent_write` still passes.

## 6. Backwards compatibility

- **Breaking, deliberately:** `--force` now requires `--force-reason`. Every in-repo
  caller updated (3 unit test files, 1 integration test file — 22 call sites). The
  CLI refusal is an actionable `parser.error`, not a traceback.
- **Not breaking:** `update-step` remains inert in a driven `single_session` run, so
  no driven pipeline is affected at all. `phase_tasks[]`-less configs (every adopted /
  standalone / legacy project, including this repo — verified: 0 phase_tasks) get a
  byte-identical handoff.
- Run-config schema root is `additionalProperties: true` and both writers persist the
  whole dict, so the new key survives every existing write path — pinned by a
  round-trip test through the real writer rather than an in-memory assertion.

## 7. Affected boundaries

| Boundary | Direction | Probe |
|---|---|---|
| `run_config.validation_overrides[]` | new write | `test_the_record_survives_the_real_config_writer` — real `update_step` → `save_run_config` → on-disk JSON → survives a later unrelated write |
| `run_config.phase_tasks[]` | new read | `test_a_phase_the_orchestrator_completed_is_reported_as_finished` — status written by the real `phase_task_lifecycle` via `single-session-apply` |
| `.shipwright/run_loop_state.json` | new read | `test_the_renderer_reads_the_loop_state_the_orchestrator_wrote` — file written by the real `loop_state.save_loop_state` |
| the loop-state path literal | duplicated constant | `test_the_consumer_and_the_producer_agree_on_the_loop_state_path` — reads the owner's constant in a subprocess |
| `PhaseTaskStatus` vocabulary | duplicated constant | `test_finished_statuses_match_the_run_config_schema` |
| `update-step` CLI args | new required pairing | 6 CLI subprocess probes incl. `--help` advertising the flag |

## Weak points I am accepting

1. **`except Exception` in `run_phase_gate` is broad.** A genuine bug in a validator
   now surfaces as an ask-level `[gate-error]` rather than a crash. That is fail-closed
   and the message carries the exception type and text, but it does trade a loud
   failure for a legible one. Accepted because the alternative — a validator crash with
   no way to complete the phase — is strictly worse, and it is what plan-review G1
   asked for.
2. **The loop-state path is duplicated.** Unavoidable (`shared/` may not import a
   plugin) and guarded by a real drift test, but it is still two places.
3. **This is the v1 path only.** A driven `single_session` run does not go through
   `update_step` at all, so item 1 protects standalone / legacy / adopted runs. That
   matches where `--force` exists; if the v2 path ever grows an override, it needs its
   own record. Noted in the module docstring and in `docs/hooks-and-pipeline.md`.
