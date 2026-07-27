# Mini-Plan — iterate-2026-07-27-phase-gate-override-evidence

Two independent items closing two already-written FR-01.01 (E) criteria.

---

## Item 1 — the phase gate runs even when overridden, and the override is recorded

### Files

| File | Change |
|---|---|
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/validation_record.py` | **new** — gate-evidence concern |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/step_planning.py` | rewire `update_step`'s complete branch |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/cli.py` | `--force-reason`; refuse `--force` without it |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/__init__.py` | re-export the new names |
| `plugins/shipwright-run/scripts/lib/orchestrator.py` | shim re-export (keeps `mocker.patch("orchestrator.X")` working) |
| `docs/hooks-and-pipeline.md` | § Phase Validators — override mechanism now records |
| `plugins/shipwright-run/tests/test_validation_override_record.py` | **new** — AC1–AC6 |

### `validation_record.py` (new module)

> **Revised after external plan review (O6).** The cap was 50 in the first draft.
> Review objected that these records are the *only* durable thing distinguishing
> "passed" from "waved through", so a small silent cap discards exactly the
> evidence the change exists to create. Final: **200**, and an eviction bumps
> `validation_overrides_dropped` so truncation is never silent.

```
MAX_VALIDATION_OVERRIDES = 200
VALIDATION_OVERRIDES_KEY  = "validation_overrides"
VALIDATION_OVERRIDES_DROPPED_KEY = "validation_overrides_dropped"

run_phase_gate(project_root, step) -> (ask_issues, inform_issues)
    lazy `from phase_validators import validate_phase`   # keeps the test patch live
    split issues by severity
    if _enforce_critical_gates_enabled():                 # unchanged semantics
        promote W5/W6/W7 FAILs into ask_issues

record_inform_notes(config, step, inform_issues)          # moved verbatim

record_validation_override(config, step, *, reason, ask_issues, inform_issues) -> record
    {step, at, reason, reason_recorded, waived, gate_result, overridden_issues, inform_count}
    append to config[VALIDATION_OVERRIDES_KEY]; keep the last 50
```

### `update_step` complete-branch, after

```
ask_issues = inform_issues = []
if not is_standalone:
    ask_issues, inform_issues = run_phase_gate(project_root, step)   # ALWAYS runs
    if ask_issues and not force:
        -> needs_validation      (unchanged: pause for a person)

... compliance subprocess (outside the lock, unchanged) ...

under run_config_lock:
    if force and not is_standalone:
        record_validation_override(config, step, reason=force_reason, ...)
    ... existing completion, unchanged ...
```

Ordering note: the gate runs **outside** `run_config_lock` (it is read-only and
slow) exactly as today; only the record-write happens under the lock, inside the
existing reload-fresh critical section. No new lock-hold.

### CLI

`--force-reason TEXT`. `--force` without it → `parser.error(...)` naming what to
pass. Library callers keep `force_reason=None` (recorded honestly as
`reason_recorded: false`) so in-repo direct callers and tests do not break.

---

## Item 2 — the handoff renders the phase status the run already holds

### Files

| File | Change |
|---|---|
| `shared/scripts/lib/handoff_pipeline.py` | **new** — `render_pipeline_phases` |
| `shared/scripts/lib/handoff_iterate.py` | **new** — `render_iterate_progress`, moved verbatim |
| `shared/scripts/tools/generate_session_handoff.py` | move `_current_iterate_progress` out; call both renderers |
| `shared/tests/test_handoff_pipeline_phases.py` | **new** — AC7–AC10 |
| `integration-tests/test_handoff_reads_real_loop_state.py` | **new** — producer→consumer round-trip |
| `docs/hooks-and-pipeline.md` | handoff artifact description |

> **Revised during build.** One combined `handoff_progress.py` landed at 304 lines,
> over the 300-LOC guideline, so it was split into the two modules above — they are
> independent anyway (one reads iterate-branch state, the other pipeline config).
>
> The first draft also planned to re-export the moved function under its old private
> name `_current_iterate_progress`. Dropped: the symbol is private, `grep` confirms the
> only references are the module itself and one in-repo test file, and a permanent
> alias for a private helper is exactly the dead compatibility surface the plan review
> objected to elsewhere (O10). The test file imports the real name instead. The five
> `test_current_iterate_progress_*` **function names** are left alone — they are node
> IDs referenced by `.shipwright/compliance/test-traceability.json`.

### `render_pipeline_phases(project_root, run_config) -> list[str]`

Inputs, both already on disk and already authoritative:

- `run_config["phase_tasks"]` — per-phase status, mutated only via
  `phase_task_lifecycle`.
- `.shipwright/run_loop_state.json` — `currentPhaseTaskId`, `attempt`, `status`.
  Read as raw JSON with a pointer comment naming the owning module; a
  `shared/` → `plugins/shipwright-run/` import is not allowed.

Output (empty list when `phase_tasks[]` is absent/empty):

```
## Pipeline Phases

Authoritative per-phase status … A phase that merely STARTED is not finished —
only `done` / `skipped` count.

- **Finished**: 3 of 7 (project, design, plan)
- **Interrupted**: `build` (split `02-ui`) — started, not finished
- **Currently dispatched**: `build` (split `02-ui`), attempt 2
- **Loop status**: running
- **Run status**: in_progress

| Phase | Split | Status | Finished? |
| … one row per phase task, interrupted rows marked **no — interrupted** … |
```

Degradation: missing / corrupt / non-dict loop state → the pointer lines are
omitted, the table still renders. Never raises.

---

## Alternative considered — and rejected

**Item 1: emit a `validation_override` event to `shipwright_events.jsonl`
instead of writing into the run config.**

For: the event log is the project's durable append-only audit surface, and
`record_event.py` already exists.

Against, and why rejected:

1. **Wrong reader.** The question the AC asks — *"was this phase waved
   through?"* — is asked of the phase's own record. `completed_steps` and
   `validation_issues` already live in the run config; a reader holding the
   config would have to know to go cross-reference a second file to learn that
   what it is looking at is not what it appears to be. The evidence belongs
   next to the claim it qualifies.
2. **`update_step` emits no events today.** Adding the first one pulls the
   events dependency into the step-advance path for one call site.
3. **Not exclusive.** The config record is the smaller, correct change now; an
   event can be added later without moving it.

Retention (last 50) is the one concession to the config-growth objection.

**Item 2: extend the existing `## Recovery` block instead of adding a section.**
Rejected — `## Recovery` is derived from the *event log* (`phase_completed`
events, counted distinct). The new block is derived from *phase-task state*.
Merging two differently-sourced views under one heading would make it impossible
for a reader to tell which one they are trusting.
