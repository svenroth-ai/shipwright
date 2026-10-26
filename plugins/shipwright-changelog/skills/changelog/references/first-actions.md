# Changelog first actions: gate policy

## Single-Session Gate Discipline

Under `mode: "single_session"` the phase's interactive gates follow a per-gate policy
(`unattended` autonomy behaves at least as `autonomous`). Resolve before you stop:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/resolve_gate_policy.py" \
  --phase changelog --list --project-root .
```

`auto-default` -> proceed with the `default_answer`; `orchestrator-approve` / `hard-stop`
-> STOP and return a gate-pending result; `interactive` -> behave as documented. Full
contract: `shared/prompts/single-session-gate-discipline.md`.

Gates: `changelog.version-suggestion` and `changelog.entry-preview` are `auto-default` (accept), matching the autonomous-mode text in Steps 4 and 5.
