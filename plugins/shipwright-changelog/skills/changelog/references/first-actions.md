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

Gates: `release.py prepare` reads this phase's rows from the gate catalog and returns `gates` (`version`, `preview`,
`out_of_sequence`: `auto` = take the catalog's default, `ask` = ask). Do what `gates` says. The catalog
(`shared/config/gate_catalog.json`) is the one source of the policy; this file and `SKILL.md` do not restate it. A dispatched
(`single_session`) run has no one to ask: a gate that is not `auto-default` there is the stop of the contract above. The phase-runner has no AskUserQuestion, and in a driven run the release PR stays open (it is not
auto-merged).
