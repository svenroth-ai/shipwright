# ADR-113 — An override overrides the verdict, never the check

**Run-ID:** `iterate-2026-07-27-phase-gate-override-evidence`
**Date:** 2026-07-27
**Status:** accepted

Long-form companion to the decision drop of the same run. Closes two acceptance
criteria that FR-01.01 already stated (REQ-3 Phase 2, #436) but the code did not
satisfy.

---

## Context

`orchestrator_pkg/step_planning.py::update_step` gated phase completion on:

```python
if not force and not is_standalone:
    valid, issues = validate_phase(step, project_root)
```

The pause half was right and stays: an ask-level finding writes
`status: "needs_validation"` and the run waits for a person. The other half was not.
With `force=True` the validator **did not run at all**, so:

- nothing knew what the gate would have said,
- nothing recorded that an override happened, or why,
- `inform`-level notes were silently dropped on that path too,
- afterwards `completed_steps` said only *"this phase completed"*. A phase that
  passed cleanly and a phase that was waved through left **byte-identical** state.

The rule requiring a person to be asked already existed. The person's answer landed
nowhere.

Separately, the generated session handoff rendered no per-phase pipeline status,
though the run already holds it: `run_config.phase_tasks[]` is authoritative and
mutated only via `phase_task_lifecycle`, and `.shipwright/run_loop_state.json` holds
the dispatch pointer. `single_session_recovery.resume_run` already reads both. The
handoff's own source comment said it "does not track in-flight phase markers".

## Decision

**Item 1 — the gate is not skippable, only its verdict is.**

- New `plugins/shipwright-run/scripts/lib/orchestrator_pkg/validation_record.py`:
  `run_phase_gate` (always runs `validate_phase` + the opt-in Phase-Quality critical
  gate), `record_inform_notes` (moved), `record_validation_override`,
  `normalise_override_reason`.
- `update_step` runs the gate whenever the run is not standalone. `force` now only
  stops ask-level findings from pausing.
- Every forced completion of a non-standalone step appends one record to
  `shipwright_run_config.json` → `validation_overrides[]`:
  `{step, at, reason, waived, gate_result, overridden_issues, inform_count}`.
  Declared in `shared/schemas/run_config.v2.schema.json`.
- A non-blank reason is **mandatory at both entry points** — `--force-reason` at the
  CLI (`parser.error`) and `normalise_override_reason` inside `update_step`
  (`ValueError`, raised before the gate runs or anything is written).
- A validator that **raises** is caught and returned as an ask-level `[gate-error]`
  issue.

**Item 2 — the handoff renders what the run already knows.**

- New `shared/scripts/lib/handoff_pipeline.py::render_pipeline_phases` emits a
  `## Pipeline Phases` block: the finished tally (`done`/`skipped` only), the
  interrupted phase(s), the loop's dispatch pointer + attempt + status, and a
  per-phase table whose verdict column says `**no — interrupted**` for `in_progress`.
- Sibling `shared/scripts/lib/handoff_iterate.py` holds the iterate renderer moved
  verbatim out of `generate_session_handoff.py` (which sits at a grandfathered bloat
  baseline and had no room).
- Nothing is computed or persisted. This is rendering only.

## Consequences

- A clean completion writes **no** record, so the presence of a record is itself the
  signal; `waived: false` / `gate_result: "pass"` distinguishes "force was used but
  nothing was actually waived" as a third state.
- **Breaking:** `--force` without `--force-reason` is refused. 22 in-repo call sites
  across 4 test files were updated.
- `update-step` remains inert in a driven `single_session` run, so no driven pipeline
  is affected — this hardens the v1 path that serves standalone / legacy / adopted
  runs, which is exactly where `--force` exists.
- Configs without `phase_tasks[]` — every adopted / standalone / legacy project,
  including this repo (verified: 0 phase tasks) — get a byte-identical handoff.
- Retention is capped at 200 and an eviction bumps `validation_overrides_dropped`, so
  a truncated log is never mistaken for a complete one.

## Rationale

The evidence belongs next to the claim it qualifies. The question *"was this phase
waved through?"* is asked of the phase's own record, and `completed_steps` /
`validation_issues` already live in the run config; a reader holding the config should
not have to know to cross-reference a second file to learn that what it is looking at
is not what it appears to be.

Enforcing the reason only at the CLI would be reopened by the next library caller — a
headless script or another plugin calling `update_step(..., force=True)` directly.

Making the gate unskippable removes whatever escape hatch skipping it provided. Before
this change, `--force` *was* the way past a broken validator. So the gate itself has to
fail legibly rather than crash: unforced it pauses fail-closed with the exception type
and message; forced it completes with the crash recorded as what was overridden.

## Alternatives rejected

**Emit a `validation_override` event to `shipwright_events.jsonl` instead.**
Wrong reader (see Rationale). Also `update_step` emits no events today, so this would
pull the events dependency into the step-advance path for one call site. Not exclusive
— an event can be added later without moving the config record.

**Cap retention at 50, matching `append_iterate_entry.py`.** This was the first draft.
External plan review objected: these records are the *only* durable thing
distinguishing "passed" from "waved through", so a small silent cap discards exactly
the evidence the change exists to create. Final: 200, plus a non-silent drop counter.

**Extend the existing `## Recovery` block instead of adding a section.** That block is
derived from the *event log* (`phase_completed` events, counted distinct). The new one
is derived from *phase-task state*. Merging two differently-sourced views under one
heading would make it impossible for a reader to tell which one they are trusting.

**Re-export the moved iterate renderer under its old private name.** Planned, then
dropped: `_current_iterate_progress` is private, `grep` finds callers only in the
defining module and one in-repo test file, and a permanent alias for a private helper
with no callers is dead compatibility surface.

**Mandatory review alone as the enforcement for item 1.** Not considered sufficient —
the same reasoning that rejected it for `touches_ci_supplychain`: a full medium iterate
with external review has already, historically, let a posture reversal through
unnoticed. The record is mechanical; a review is not.

## Verification

- 14 of 23 new item-1 tests fail against the pre-change gate condition; the item-2
  end-to-end test fails with the renderer unwired. The tests falsify.
- Boundary round-trips drive the **real** producers (`create_config` +
  `phase_task_lifecycle` + `loop_state.save_loop_state` via the orchestrator CLI)
  rather than hand-written fixtures, and a subprocess drift-guard asserts the shared
  consumer and the run plugin agree on the loop-state path.
- Suites: 4990 shared · 376 shipwright-run · 421 integration · 84 shipwright-build ·
  `ruff` clean · anti-ratchet clean.
