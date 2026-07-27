# Iterate: Phase-gate override leaves evidence; handoff renders phase status

- **Run ID:** iterate-2026-07-27-phase-gate-override-evidence
- **Date:** 2026-07-27
- **Type:** change
- **Complexity:** medium
- **Branch:** iterate/phase-gate-override-evidence
- **Spec Impact:** NONE — see *Spec Impact* below
- **Risk flags:** none by the authoritative diff-driven detectors — see *Risk flags* below
- **Intent:** Make two already-written FR-01.01 acceptance criteria true in code.

---

## Problem

`.shipwright/planning/01-adopted/spec.md` FR-01.01 already states both of these
as (E) acceptance criteria (added by REQ-3 Phase 2, #436). Neither is satisfied
by the code.

### Item 1 — overriding a phase gate leaves no trace, and skips the check

> FR-01.01 (E): *"Given a person decides to go ahead regardless, when the phase
> is marked finished anyway, then what was overridden and why is recorded — so
> afterwards 'passed its checks' and 'was waved through' can still be told
> apart."*

`orchestrator_pkg/step_planning.py::update_step` gates completion on
`validate_phase`. An ask-level issue writes `status: "needs_validation"` and the
run pauses for a person — that half is right and stays.

What is wrong is the other half:

```python
if not force and not is_standalone:      # step_planning.py:152
    from phase_validators import validate_phase
    valid, issues = validate_phase(step, project_root)
```

With `force=True` the validator **does not run at all**. So:

- nothing knows what the gate would have said,
- nothing records that an override happened, or why,
- `inform`-level notes are silently dropped on the force path too,
- afterwards `completed_steps` says only *"this phase completed"* — a phase that
  passed cleanly and a phase that was waved through are byte-identical.

The rule requiring a person to be asked already exists. The person's answer
lands nowhere.

### Item 2 — the handoff does not show state the run already holds

> FR-01.01 (E): *"…the document a person reads on returning states which phases
> are finished and which one was interrupted — the run already knows this; the
> point is that the person is told without having to ask."*

The authoritative per-phase status is `shipwright_run_config.json` →
`phase_tasks[]`, mutated only through `phase_task_lifecycle`. Which phase is
currently dispatched is `.shipwright/run_loop_state.json` → `currentPhaseTaskId`
(+ `attempt`, `status`). `single_session_recovery.resume_run` already reads both.

`shared/scripts/tools/generate_session_handoff.py` renders neither. Its own
source comment says so (`_current_iterate_progress`, line 236):

> *"The rest of the handoff is an overview of completed work (iterate_history,
> recent events); it does not track in-flight phase markers."*

The nearest thing it does render — `## Recovery` → `**Pipeline**: N phases
completed` — counts distinct `phase_completed` **events**, not phase-task state,
and says nothing about what was interrupted.

**This is a presentation gap, not missing state.** Nothing needs to be built to
make the run resumable; it already is. What is missing is rendering what is
already known.

---

## Scope

**OWNS:** the orchestrator's step-advance path (`update_step` + its CLI) and the
session-handoff renderer. Independently executable. Touches no workflow file and
no other plugin's behaviour.

**Out of scope (deliberate):**

- `single-session-apply` / `phase_task_lifecycle` — the v2 completion path has no
  `--force`, so item 1 does not apply to it. Left untouched.
- Building resume state. Item 2 is rendering only.
- Surfacing item 1's override records inside item 2's handoff block.
  `validation_overrides` is keyed by v1 **step name**; `phase_tasks[]` is the v2
  model. They are different state tracks and joining them in one table would
  imply a correspondence that does not exist.

---

## Acceptance Criteria

### AC1 — the gate runs even when overridden
Given a non-standalone run and `update_step(step, "complete", force=True)`,
when the step completes, then `validate_phase` **was called** and its findings
were captured.

### AC2 — an override is recorded with what it overrode and why
Given the gate returned ask-level issues and a person supplied a reason,
when the step completes under force, then `shipwright_run_config.json` gains a
`validation_overrides[]` entry carrying the step, the timestamp, the reason, and
the ask-level findings verbatim, with `waived: true`.

### AC3 — "passed" and "waved through" are distinguishable afterwards
Given a step that completed with a clean gate and no force,
when the config is read afterwards, then it carries **no** override record for
that step — so the presence of a record is itself the signal. A forced
completion over a *clean* gate records `waived: false` / `gate_result: "pass"`,
so "force was used but nothing was actually waived" is also distinguishable.

### AC4 — the reason must actually be supplied at the CLI
Given `orchestrator.py update-step --status complete --force` with no
`--force-reason`, when it is invoked, then it is refused with an actionable
message rather than recording an override with an empty reason.

### AC5 — the existing pause rule is unchanged
Given ask-level issues and **no** force, when completion is attempted, then
`status` is `needs_validation`, `validation_issues` is populated, and the step is
not appended to `completed_steps` — exactly as before.

### AC6 — standalone still skips the gate
Given a standalone (bare-phase) invocation, when a step completes, then
`validate_phase` is not called and no override record is written — there is no
interactive person to override, so nothing was overridden.

### AC7 — the handoff states which phases are finished
Given a run config with `phase_tasks[]`, when the handoff is generated, then it
renders a per-phase table plus a finished tally counting only `done` / `skipped`.

### AC8 — the handoff states which phase was interrupted, and that started ≠ finished
Given a phase task in `in_progress`, when the handoff is generated, then that
phase is named as interrupted, is excluded from the finished tally, and the
block states in words that a phase which merely started does not count as
finished.

### AC9 — the handoff shows the dispatch pointer the loop already holds
Given `.shipwright/run_loop_state.json`, when the handoff is generated, then the
currently-dispatched phase task, its attempt count, and the loop status are
rendered.

### AC10 — no phase_tasks renders nothing
Given a legacy / standalone config with no `phase_tasks[]`, when the handoff is
generated, then the pipeline block is absent entirely — no placeholder rows.

---

## Spec Impact — NONE (justification)

Both behaviours are **already stated verbatim** as (E) acceptance criteria on
FR-01.01 (`.shipwright/planning/01-adopted/spec.md:67-74`), landed by REQ-3
Phase 2 (#436). This iterate makes the code satisfy requirement text that
already exists. Adding a new (E) bullet would duplicate FR-01.01 bullets 3 and 4.
No requirement is added, modified, or removed.

---

## Affected Boundaries

| Boundary | Direction | Producer | Consumer (this diff) |
|---|---|---|---|
| `shipwright_run_config.json` → `validation_overrides[]` | write | `update_step` (new) | audit / future readers |
| `shipwright_run_config.json` → `phase_tasks[]` | read | `phase_task_lifecycle` | handoff renderer (new) |
| `.shipwright/run_loop_state.json` | read | `single_session/loop_state.py` | handoff renderer (new) |
| `orchestrator.py update-step` CLI | args | operator / phase skills | new `--force-reason` |

## Risk flags — classifier output vs. the diff

`classify_complexity.py` reported `touches_auth` from the **prompt text**. Recomputed
against the actual diff with the authoritative detectors
(`plugins/shipwright-iterate/scripts/lib/risk_detectors.py`, 27 changed files):

| Flag | Diff-driven verdict |
|---|---|
| `touches_auth` | **false positive** — keyword match on the prose word *"authoritative"*. No changed path contains `auth`. |
| `cross_component` | `False` — no `hooks.json`, no `hooks/*.py`, no `verify_phase`/`get_phase_context`, no merge/churn/event-log resolver, no campaign machinery. |
| `touches_io_boundary` | `False` |
| `touches_ci_supplychain` | `False` — no workflow file touched, as the brief scoped. |
| `touches_build` | `False` |

Complexity stays **medium** (history prior, n=20); no risk floor applied.

**But the boundary probes were run anyway, and that is the interesting part.**
`is_io_boundary_change` matches on *file paths* — `.env*`, `hooks.json`,
`*_config.json`, `*_state.json`. This diff adds a pure **consumer** of
`run_config.phase_tasks[]` and `.shipwright/run_loop_state.json` inside a `.py` file
and changes neither JSON file, so the path heuristic cannot see it. The detector's own
docstring already records that AST-pair producer/consumer detection is deliberately
deferred; this diff is a live instance of the gap, not a counter-example to the
decision. Treated as boundary-touching on the merits: the round-trip tests drive the
real producers rather than hand-written fixtures.

---

## Design

### Item 1

New `plugins/shipwright-run/scripts/lib/orchestrator_pkg/validation_record.py`
(< 300 LOC) holding the gate-evidence concern:

- `run_phase_gate(project_root, step) -> (ask_issues, inform_issues)` — runs
  `validate_phase` (lazy import, so `mocker.patch("phase_validators.validate_phase")`
  keeps intercepting) plus the opt-in Phase-Quality critical gate.
- `record_inform_notes(config, step, inform_issues)` — moved verbatim.
- `record_validation_override(config, step, *, reason, ask_issues, inform_issues)`
  — appends one entry to `config["validation_overrides"]`, retention-capped at 50
  (matching `append_iterate_entry.py`'s convention).

`update_step` becomes: run the gate whenever not standalone; pause only when
there are ask issues **and** not force; record an override entry whenever force
was used on a non-standalone run.

`cli.py` gains `--force-reason` and refuses `--force` without it.

**Why a new module:** `step_planning.py` is 245 LOC against the 300 limit —
adding the record-keeping inline would take it to ~290 and leave nothing for the
next change. The extraction keeps the step-advance path readable and the new
concern testable on its own.

### Item 2

New `shared/scripts/lib/handoff_progress.py` (< 300 LOC) holding the two
handoff progress renderers:

- `render_iterate_progress(...)` — **moved verbatim** from
  `generate_session_handoff.py` (re-exported under its old private name so the
  existing test imports keep resolving).
- `render_pipeline_phases(project_root, run_config)` — new. Reads
  `phase_tasks[]` from the run config the caller already loaded, and
  `.shipwright/run_loop_state.json` directly (a 3-line JSON read; a cross-plugin
  import from `shared/` into `plugins/shipwright-run/` is forbidden here, so the
  path literal is duplicated with a pointer comment naming its owner).

**Why a move, not just an addition:** `generate_session_handoff.py` is at 669
lines with a `grandfathered` bloat-baseline entry of exactly 669. Any net growth
ratchets it and the pre-commit anti-ratchet hook blocks the commit. Moving the
~108-line `_current_iterate_progress` out makes room and puts both progress
renderers in one place.

---

## Confidence Calibration

- **Boundaries touched:** `shipwright_run_config.json` (`validation_overrides[]`
  write, `phase_tasks[]` read), `.shipwright/run_loop_state.json` (read),
  `orchestrator.py update-step` CLI args, the duplicated `LOOP_STATE_REL_PATH` and
  `PhaseTaskStatus` constants.

- **Empirical probes run** (each one a thing I did not know until I ran it):

  | Probe | Finding |
  |---|---|
  | Revert `step_planning.py` to the pre-change gate condition, re-run the new suite | **14 of 23 red.** The 9 green are regression pins on unchanged behaviour, which is correct. The tests falsify. |
  | Unwire `render_pipeline_phases`, re-run the item-2 suite | The end-to-end test goes red; the 17 unit tests stay green (they call the renderer directly). Wiring is genuinely covered. |
  | Drive `update-step --force` through the **CLI** against a `create_config` fixture | Returned `{driven_run: true, state_mutated: false}` — `--force` is **unreachable** on a `mode: single_session` config. Both test fixtures were changed to mode-less configs so they exercise a state that can actually occur. Would have shipped a test proving nothing. |
  | `grep` the run-config schema for `additionalProperties` | Root is `true`, and `save_run_config` / `_write_config` both persist the whole dict — nothing drops unknown keys. Declared the field anyway. |
  | `grep -rn "_current_iterate_progress"` before moving it | Defining module + one in-repo test file only. No external caller ⇒ no compat alias needed. |
  | Read `run_config.v2.schema.json` `$defs.PhaseTaskStatus` | Six statuses, not the three assumed. `failed` is terminal but **not** finished and now renders distinctly. |
  | Run the anti-ratchet pre-commit hook | Blocked on two grandfathered test files that grew by 5 and 8 lines. Both shrunk back under baseline; `generate_session_handoff.py` baseline lowered 669 → 569. |
  | Read this repo's own `shipwright_run_config.json` | 0 `phase_tasks`, mode-less, non-standalone ⇒ its handoff is unchanged by item 2, and item 1's path **is** live for it. |
  | Full suites | 4990 shared · 376 shipwright-run · 421 integration · 84 shipwright-build · `ruff` clean. |

- **Test Completeness Ledger** — every behaviour this diff introduces or changes.
  Principle: *testable ⇒ tested*. 0 testable-but-untested.

  | # | Behaviour | Disposition | Evidence |
  |---|---|---|---|
  | 1 | The phase gate runs even under `--force` | `tested` | `test_force_still_runs_the_phase_gate` |
  | 2 | A forced completion records step/time/reason/findings | `tested` | `test_a_waved_through_completion_is_recorded_with_what_and_why` |
  | 3 | A clean unforced completion records nothing | `tested` | `test_a_clean_completion_records_no_override` |
  | 4 | Force over a clean gate records `waived:false` / `pass` | `tested` | `test_force_over_a_clean_gate_records_a_pass_not_a_waiver` |
  | 5 | The record survives the real config writer to disk | `tested` | `test_the_record_survives_the_real_config_writer` |
  | 6 | Ask-level issues without force still pause the run | `tested` | `test_ask_issues_without_force_still_pause_the_run` |
  | 7 | A forced retry clears stale `validation_issues` | `tested` | `test_a_forced_retry_clears_the_stale_pause_issues` |
  | 8 | Blank/absent reason is refused before any read or write | `tested` | `test_force_without_a_reason_is_refused_before_anything_is_written` (4 params) |
  | 9 | The CLI refuses `--force` without `--force-reason` | `tested` | `test_force_without_a_reason_is_refused`, `test_a_whitespace_only_reason_is_refused_too` |
  | 10 | A CLI reason reaches the durable record | `tested` | `test_a_reason_given_on_the_command_line_reaches_the_record` |
  | 11 | `--force-reason` is discoverable in `--help` | `tested` | `test_the_flag_is_advertised_in_help` |
  | 12 | Standalone skips the gate and records nothing | `tested` | `test_standalone_skips_the_gate_and_records_nothing` |
  | 13 | A crashing validator does not wedge the force path | `tested` | `test_a_crashing_validator_does_not_wedge_the_force_path` |
  | 14 | A crashing validator pauses the unforced path | `tested` | `test_a_crashing_validator_pauses_the_unforced_path` |
  | 15 | Inform notes are recorded on the forced path too | `tested` | `test_inform_notes_are_recorded_on_the_forced_path_too` |
  | 16 | Critical-gate FAILs keep their semantics + are overridable | `tested` | `test_critical_gate_failures_are_overridable_and_recorded` |
  | 17 | Retention is capped and evictions are counted | `tested` | `test_override_retention_is_capped_and_the_drop_is_counted` |
  | 18 | The lazy `validate_phase` import keeps the patch target live | `tested` | `test_the_validate_phase_patch_target_still_intercepts` |
  | 19 | Finished phases are named and tallied | `tested` | `test_finished_phases_are_named_and_tallied` |
  | 20 | The interrupted phase is named as interrupted | `tested` | `test_the_interrupted_phase_is_named_as_interrupted` |
  | 21 | A started phase is not counted as finished | `tested` | `test_a_phase_that_merely_started_does_not_count_as_finished` |
  | 22 | Nothing mid-flight says so explicitly | `tested` | `test_a_run_with_nothing_mid_flight_says_so` |
  | 23 | `failed` is terminal but not finished | `tested` | `test_a_failed_phase_is_not_counted_as_finished_either` |
  | 24 | The dispatch pointer + attempt + loop status render | `tested` | `test_the_dispatch_pointer_is_rendered` |
  | 25 | An unresolvable pointer renders as stale, not as a phase | `tested` | `test_a_pointer_naming_no_known_task_is_labelled_stale` |
  | 26 | A non-numeric attempt is omitted | `tested` | `test_a_non_numeric_attempt_is_omitted_rather_than_printed` |
  | 27 | Absent / corrupt / non-object loop state degrades | `tested` | 3 tests (`no_loop_state`, `corrupt`, `not_an_object`) |
  | 28 | Multiple `in_progress` tasks are all named | `tested` | `test_multiple_in_progress_tasks_are_all_named` |
  | 29 | `\|` and newlines in producer data cannot break the table | `tested` | `test_markdown_delimiters_in_producer_data_cannot_break_the_table` |
  | 30 | Non-mapping `phase_tasks` rows are skipped | `tested` | `test_non_mapping_rows_are_skipped` |
  | 31 | No `phase_tasks` ⇒ no block, no placeholders | `tested` | `test_a_config_without_phase_tasks_renders_nothing`, `test_a_legacy_project_handoff_gains_no_pipeline_block` |
  | 32 | The block renders above the legacy checkpoint end-to-end | `tested` | `test_generate_handoff_renders_the_block_above_the_legacy_checkpoint` |
  | 33 | Consumer and producer agree on the loop-state path | `tested` | `test_the_consumer_and_the_producer_agree_on_the_loop_state_path` |
  | 34 | `FINISHED_STATUSES` ⊆ the schema's declared enum | `tested` | `test_finished_statuses_match_the_run_config_schema` |
  | 35 | The renderer reads loop state the orchestrator really wrote | `tested` | `test_the_renderer_reads_the_loop_state_the_orchestrator_wrote` |
  | 36 | A really-completed phase flips from interrupted to finished | `tested` | `test_a_phase_the_orchestrator_completed_is_reported_as_finished` |
  | 37 | Docs (`hooks-and-pipeline.md`, `guide.md`, `constitution.md`) describe the new contract | `untestable` — `requires-manual-visual-judgment` | Prose accuracy; reviewed against the diff by hand |

  **Untestable: 1 of 37**, with a closed-vocabulary reason code. Testable-but-untested: **0**.

- **Confidence-pattern check:**
  - *Asymptote (depth).* The two deepest risks are both empirically pinned rather
    than argued: the record really reaches disk through the real writer and survives
    a later write, and the renderer really reads files the real orchestrator wrote
    (not a fixture I authored to match my own assumptions).
  - *Coverage (breadth).* Every branch of both new functions is exercised, including
    all four degradation paths of `_read_loop_state` and all four verdicts of
    `_finished_verdict`. The two duplicated constants each have a drift-guard that
    fails here when the owner changes over there.
  - *Integration composition.* `cross_component` does **not** apply — recomputed
    from the diff against `risk_detectors.CROSS_COMPONENT_FILE_PATTERNS`, no changed
    path matches (no `hooks.json`, no `hooks/*.py`, no `verify_phase` /
    `get_phase_context`, no merge/churn/event-log resolver, no campaign machinery).
    An integration test is nevertheless present, because `touches_io_boundary` does
    apply and a hand-written fixture would have proved nothing about the real
    producers.
  - *Known residual.* `except Exception` in `run_phase_gate` converts a validator
    bug into a legible ask-level finding rather than a crash — a deliberate trade
    (plan-review G1), recorded in the self-review's "weak points I am accepting".
