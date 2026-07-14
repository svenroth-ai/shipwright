# C. Detect Invocation Mode — full decision tree

**The `phaseTaskId` the orchestrator hands you at dispatch is the authority** — NOT any
state field inside `shipwright_run_config.json`. The pipeline's v1 state fields are no
longer advanced, so keying on them made every driven phase past the first misclassify
itself as standalone; the rationale is in `shared/scripts/lib/phase_invocation_mode.py`.
**Never re-derive the mode yourself.** Ask the resolver:

```bash
uv run "{shared_root}/scripts/tools/get_phase_context.py" \
  --phase-task-id "{phaseTaskId}" --phase design --project-root "{project_root}"
```

Omit `--phase-task-id` if you were not handed one. Set `invocation_mode` from the returned
`mode`, which is exactly one of:

- **`pipeline`** — you were dispatched. Enforce gates, and do the phase's real work.
  **Do NOT call `orchestrator.py update-step`** (nor any other run-state write): in a
  driven run `single-session-apply` owns phase completion — it records your status when
  it applies your result. See `plugins/shipwright-run/skills/run/SKILL.md`. (`update-step`
  is inert in a driven run anyway, but do not rely on that.)
- **`standalone`** — no token, so this is a hand-invoked run:
  - Skip pipeline state updates (no `orchestrator.py update-step` calls)
  - Skip upstream completion checks
  - Still produce all artifacts (mockup HTML files, design-manifest.md)
  - If no `shipwright_project_config.json` exists, work with whatever specs are available in `.shipwright/planning/`. If none exist, ask user to describe what screens they need.
  - Print: `"Running in standalone mode — pipeline state will not be updated."`
  - If `requires_out_of_sequence_warning` is `true`, a driven run is LIVE at
    `active_phases`. Warn that running `/shipwright-design` out-of-band may collide with
    it, and **ask the user before continuing** (gate `design.out-of-sequence-continue`).
- **`error`** (exit code 2) — you were dispatched but the token does not resolve (stale,
  terminal, wrong phase, or an unreadable config). **STOP.** Do NOT continue as
  standalone: that is precisely what stamps a driven run's artifacts `"mode": "standalone"`
  and deadlocks the pipeline. Surface it to the orchestrator as an `ok: false` result.

Store the resolver's verdict as `invocation_mode` — `"pipeline"` | `"standalone"` | `"error"` (STOP) — for use in later steps.

**Single-Session Gate Discipline:** under `mode: "single_session"`, honour per-gate policies — resolve interactive gates via `${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/resolve_gate_policy.py --phase design --list` before stopping (`auto-default` → proceed; `orchestrator-approve`/`hard-stop` → STOP; `design.preview-approval` + `design.review-loop-finalize` are orchestrator-approve — a human eyeballs the mockups). Full rule: `shared/prompts/single-session-gate-discipline.md`.
