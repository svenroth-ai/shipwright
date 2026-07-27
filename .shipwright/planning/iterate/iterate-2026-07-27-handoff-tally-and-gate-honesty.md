# Iterate: the handoff tally stops overstating, and the gate stops minting a pass it did not earn

- **Run ID:** iterate-2026-07-27-handoff-tally-and-gate-honesty
- **Date:** 2026-07-27
- **Type:** bug
- **Complexity:** medium
- **Branch:** iterate/handoff-tally-and-gate-honesty
- **Spec Impact:** NONE — see *Spec Impact* below
- **Predecessor:** `iterate-2026-07-27-phase-gate-override-evidence` (PR #438, merged f6179f6e)

---

## Problem

The predecessor shipped two things whose whole purpose is **telling a person the
truth about state**: a `## Pipeline Phases` block in the session handoff, and a
durable `validation_overrides[]` record. A Stage-2 code review and a Stage-3
doubt review — run after the merge — found that both say things that are not so.

Every defect below is a *false statement to a human reader*, which is the exact
failure class the predecessor existed to remove. That is what makes this a bug
iterate rather than a polish pass.

### Root causes (established, not assumed)

**R1 — the finished tally denominates against the wrong set.**
`render_pipeline_phases` computes `len(finished) of len(tasks)` over
`run_config["phase_tasks"]`. But phase tasks are materialised **one at a time**:
`config_factory.py:160` seeds `"phase_tasks": [initial_task]` — a single project
task — and successors are appended by `plan_next_phase` as each phase completes.
So the denominator is *tasks created so far*, not the pipeline length. A run that
has finished 1 of 7 phases renders **`Finished: 1 of 2`**. The block calls itself
"Authoritative per-phase status", and the overstatement is worst at the start —
exactly when someone is most likely to be resuming. `run_config["pipeline"]` (the
real 7-step list) is already in the dict the renderer receives.

*Verified:* `plugins/shipwright-run/scripts/lib/orchestrator_pkg/config_factory.py:160`.

**R2 — a pointer at an undispatched task is labelled "Currently dispatched".**
`loop_state.advance_pointer` moves `currentPhaseTaskId` to the **successor** and
resets `attempt` to 0; only `record_dispatch` raises it to ≥ 1 at an actual
dispatch. So the persisted state between two phases — last phase applied, next
not yet started, the single most common interruption point — renders
`- **Currently dispatched**: \`design\` (status \`awaiting_launch\`, attempt 0)`
next to `- **Interrupted**: none`. A reader concludes a design run is in flight.

*Verified:* `single_session/loop_state.py:108-127` + `single_session_apply.py:71-85`.

**R3 — a forced retry leaves `status: "needs_validation"` behind.**
The complete-branch pops `validation_issues` but assigns `status` only when the
pipeline finishes or in the split-loop. After the documented pause → `--force`
flow the config carries `completed_steps=[…step]`, an advanced `current_step`,
**and** `status: "needs_validation"`. The predecessor's own in-code comment
asserts the opposite ("a completed step never carries findings that imply it is
still stuck"), and its test `test_a_forced_retry_clears_the_stale_pause_issues`
asserts only `"validation_issues" not in config` — one assertion short of
catching it. `update_build_dashboard.py:100` and `resolve_next_dispatch` both key
on that field.

**R4 — a step with no validator records `gate_result: "pass"`.**
`validate_phase` returns `(True, [])` when `_VALIDATORS.get(step)` is None.
`security` is an accepted `--step` (`cli.py`: `PIPELINE_STEPS + ["security"]`) and
has no `_VALIDATORS` entry. A forced completion therefore writes a durable record
asserting the gate **passed** where no gate exists — byte-identical to a genuine
clean-gate override. The record is the one artifact that must not lie.

*Verified:* `phase_validators.py:81-84` + `:486-495` (no `security` key).

**R5 — the finished list drops the split, so a phase reads as finished and
interrupted at once.** The tally renders bare `phase` names while the Interrupted
line renders phase + split. A standard multi-split run
(`plan/01 done, build/01 done, plan/02 done, build/02 in_progress`) reads
`Finished: 3 of 4 (project, plan, build)` **and** `Interrupted: \`build\` (split \`02\`)`.
Worse, a **failed** task appears in *no* bullet at all — a run that died at build
renders `Interrupted: none — no phase is mid-flight`, i.e. "nothing to pick up"
for a dead run.

**R6 — the drift guard checks the direction its docstring disclaims.**
`test_finished_statuses_match_the_run_config_schema` asserts
`FINISHED_STATUSES <= declared` while its docstring promises "a new terminal
status added there must not leave this renderer silently miscounting". A seventh
status added to `$defs.PhaseTaskStatus` keeps the subset assertion green while
`_finished_verdict` silently falls through to `"no"`. The Confidence Calibration
of the predecessor credited this test with drift protection it does not provide.

**R7 — an unhashable status crashes the renderer.**
`t.get("status") in FINISHED_STATUSES` raises `TypeError: unhashable type` for a
malformed `status` (list/dict). The module hardens against every other
malformed-producer shape — non-mapping rows, `|`, newlines, corrupt loop state —
so this is the one hole. The Stop hook's outer `except Exception` converts it
into a **silently skipped handoff**, which is the worse outcome for a document
whose job is telling a person where they are.

**R8 — the critical-gate block can discard the findings it was meant to add.**
`run_phase_gate`'s `try` wraps both `validate_phase` **and** the Phase-Quality
block. If `_read_latest_phase_quality_finding` raises (it `stat()`s inside a
`sorted()` key over a glob — a file vanishing between glob and stat is realistic
on Windows), the ask/inform issues already computed are **replaced** by the single
synthetic `[gate-error]`. The override record then misrepresents what was
overridden.

**R9 — inform notes now duplicate and are uncapped.**
The gate re-runs under force, so the pause → force flow appends the same inform
issues twice; `record_inform_notes` neither dedups nor clears, and
`validation_notes` has no retention cap. `update_build_dashboard.py:104` renders
one line per entry into a **tracked** artifact, so the duplication is visible and
grows per split-loop pass.

**R10 — the gate error loses its traceback.** The synthetic issue carries
`type(exc).__name__: exc` and nothing else; the exception is swallowed and never
re-raised, so a validator bug now has no frame information anywhere. Before the
predecessor it produced a full traceback.

**R11 — CLI and library disagree on when a reason is required.** The CLI check
fires for any `--status` and **before** the drivability guard; `update_step`
enforces only inside `status == "complete"` and `not is_standalone`. So
`update_step(root, step, "in_progress", force=True)` is accepted by the library
and rejected by the CLI, and a driven run that used to print
`{driven_run: true, state_mutated: false}` and exit 0 now exits 2.

---

## Scope

**In:** `shared/scripts/lib/handoff_pipeline.py`,
`plugins/shipwright-run/scripts/lib/orchestrator_pkg/{step_planning,validation_record,cli}.py`,
their tests, and the stale Design section of the predecessor's spec.

**Out, deliberately:**

- **The silent standalone demotion on a corrupt config.** `_read_standalone_flag`
  returns `True` when `load_run_config` fails to parse, so the whole override
  guarantee switches itself off and `_load_or_bootstrap` can overwrite a real
  config. Real and worth fixing — but it **predates** the predecessor
  (`run_config_store.py` already names it), its blast radius is every v1 caller,
  not just the override path, and fixing it means deciding what "corrupt config"
  should do to a run. Separate iterate; filed rather than smuggled in here.
- **Surfacing `validation_overrides[]` to a human** (dashboard / RTM). A feature,
  not a defect — the record is correct and readable, just not rendered.
- Re-litigating the predecessor's change-sizing.

---

## Acceptance Criteria

### AC1 — the tally counts against the pipeline, not against what has been planned
Given a run whose `phase_tasks[]` holds fewer entries than `pipeline`, when the
handoff renders, then the finished tally denominates against the real pipeline
length and the block states that phase tasks are planned incrementally. A run
1 of 7 phases in never reads as "1 of 2".

### AC2 — a task that was never dispatched is not called dispatched
Given `attempt` 0 or absent (the pointer parked on a successor), when the handoff
renders, then that task is labelled as next up and explicitly *not yet
dispatched*.

"Currently dispatched" requires positive evidence of a dispatch: an attempt
counter `>= 1` **or** the pointed task's own status being `in_progress`. The
status is the stronger signal of the two — `claim_phase_task` sets it under CAS
at dispatch time, while `attempt` is a retry counter that recovery resets — so a
task the lifecycle records as `in_progress` is dispatched regardless of what the
counter says. (An earlier draft of this criterion said "only for `attempt >= 1`";
external code review caught that the code and the criterion disagreed. The code
is right and the criterion was corrected, not the other way round.)

### AC3 — a forced retry clears the pause marker
Given a step paused at `needs_validation` and then completed under `--force`,
when the config is read, then `status` is no longer `needs_validation` (and the
pipeline-complete assignment still wins when nothing remains).

### AC4 — a step with no validator does not record a pass
Given a `--step` with no `_VALIDATORS` entry, when it completes under force, then
the record carries `gate_result: "not_checked"` and `waived: false` — never
`"pass"`.

### AC5 — the finished list is unambiguous under splits, and failures are named
Given multi-split phase tasks, when the handoff renders, then finished entries
carry their split, and any `failed` task is named in its own bullet rather than
being absent from every bullet.

### AC6 — the drift guard fails on an unclassified new status
Given a status added to `$defs.PhaseTaskStatus` that the renderer does not
classify, when the suite runs, then the drift test fails.

### AC7 — a malformed status degrades instead of crashing
Given a `phase_tasks[]` entry whose `status` is a list or dict, when the handoff
renders, then it renders without raising and shows the row as unknown.

### AC8 — a critical-gate failure adds to the findings, it does not replace them
Given `validate_phase` succeeded and the Phase-Quality lookup then raises, when
the gate returns, then the real findings survive and the gate error is appended.

### AC9 — inform notes do not accumulate duplicates
Given the pause → force flow, when the config is read, then the step's inform
notes appear once.

### AC10 — a gate crash keeps its traceback
Given a validator that raises, when the gate catches it, then the traceback
reaches stderr while the record stays compact.

### AC11 — CLI and library enforce the same precondition
Given `--force` with a non-`complete` status, or a driven `single_session` run,
when `update-step` runs, then the CLI behaves as `update_step` does — the
drivability guard still short-circuits first and stays inert.

---

## Spec Impact — NONE (justification)

FR-01.01 already states the governing criteria; the predecessor closed them and
this iterate fixes defects in that implementation. No requirement text changes —
these are wrong answers to questions already asked, not new questions.

---

## Affected Boundaries

| Boundary | Direction | Note |
|---|---|---|
| `run_config.phase_tasks[]` + `pipeline` | read | new denominator source |
| `.shipwright/run_loop_state.json` (`attempt`) | read | now semantically interpreted, not just printed |
| `run_config.validation_overrides[].gate_result` | write | new `not_checked` value → schema update |
| `run_config.status` | write | forced retry now clears `needs_validation` |
| `run_config.validation_notes` | write | dedup |

## Confidence Calibration

- **Boundaries touched:** as above.
- **Empirical probes run:** *(Step 7.5)*
- **Test Completeness Ledger:** *(Step 7.5)*
- **Confidence-pattern check:** *(Step 7.5)*
