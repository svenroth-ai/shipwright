# Step 0 — Phase Session Context Recovery

If the orchestrator handed you a `phaseTaskId` — i.e. `/shipwright-run` dispatched
you as a phase-runner subagent — you are part of an active pipeline. Run this as your
very first action:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/get_phase_context.py" \
  --phase-task-id <phaseTaskId-from-context>
```

The tool prints structured JSON with `runId`, `phase`, `splitId`, `prerequisites`,
`runConditions`, and a `skill_artifacts_to_read` list. Read those artifacts
before proceeding so this phase session has full context for what came before.

If NO `phaseTaskId` was handed to you, this is a standalone invocation —
continue with Step 1 below as normal.

**One resolver, one verdict.** This is the same tool your "Detect Invocation Mode" step
already ran, so reuse that payload rather than re-deriving anything: its `mode` IS your
`invocation_mode`. Pass `--phase <your phase>` so a token belonging to another phase is
rejected, and if `mode` is `"error"` (exit 2) **STOP** — a dispatched phase must never
fall back to standalone.
