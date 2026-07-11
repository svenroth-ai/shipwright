# Phase Timing — Iterate-Rail durations (M-Pre-1 iterate half)

The WebUI Iterate-Rail shows real time-per-node for the 5 display groups
(`scope → build → review → test → finalize`). B1 gave the *pipeline* rail this
via paired `phase_started`/`phase_completed`; the iterate flow writes a single
`work_completed` event and its phases are LLM-executed SKILL steps, so instead we
emit a lightweight boundary **mark** as each group boundary is crossed and let
`finalize_iterate` (F5b) fold the durations into `work_completed.phase_timings`.

**Additive and best-effort** — a skipped mark just omits that node's bar; never
block on it. A run with no marks records no `phase_timings` (pre-M-Pre-1 and
partial-mark history degrade gracefully; the WebUI reads the field only when
present).

## The 5 marks

| Mark | Emit when | Anchor |
|---|---|---|
| `scope` | run_id exists, **before** Repo Scout | §C (right after Generate Run ID) |
| `build` | entering Build (TDD) | Step 6 |
| `review` | entering Self-Review | Step 7 |
| `test` | entering the fresh full-suite gate | F0 |
| `finalize` | entering finalization-proper | F1 |

**Timing anchors are chronological, so two `scope`-adjacent phases don't land in
their `session_plan` logical group — disclosed, not silent:**
- `scope` is marked at §C so Repo Scout (§E, `repo_scout` ∈ `scope`) IS captured.
- The pre-F0 test layers (browser/E2E) fall in the `review`→`test` window; F0 (the
  mandatory fresh full-suite re-run) anchors the Test node.
- `external_plan_review` (logically `review` in `session_plan`) runs before Build,
  so its time counts under the **`scope`** node, not `review`. The `review` node
  measures self-review + full code review + confidence calibration. This is a
  minor, display-only approximation of the join — acceptable because durations are
  a WebUI nicety, not a control signal.

## Command

Run once per boundary (first-wins, so a re-cross is a safe no-op). Best-effort —
suffix `|| true` so a transient mark failure never blocks the iterate:

```bash
uv run "{shared_root}/scripts/tools/iterate_phase_timing.py" \
  mark <group> --project-root "{project_root}" --run-id "{run_id}" || true
```

## Contract

- Group ids are the SSoT `scope build review test finalize`
  (`shared/scripts/lib/iterate_phase_groups.py`, pinned to the Plan-Card grouping
  in `session_plan._PHASE_CATALOG` so the WebUI can join phases-per-group with
  duration-per-group).
- The sidecar `.shipwright/agent_docs/iterates/<run_id>.phase_timings.jsonl` is
  **gitignored** (sibling of `<run_id>.plan.json`); the durable copy is the
  tracked `work_completed.phase_timings` field (`[{phase, started, duration_ms}]`).
- `finalize_iterate` folds it automatically at F5b (via
  `lib.iterate_phase_groups.fold_into_event`, validated by the shared
  `normalize_phase_timings`) — you do **not** pass timings on the CLI.
