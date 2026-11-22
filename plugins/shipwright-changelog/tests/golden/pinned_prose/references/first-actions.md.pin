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

Gates: `changelog.version-suggestion` (Step 4) and `changelog.entry-preview` (Step 5) are `auto-default` (accept).

**Driven run, stated plainly:** in a driven (`single_session`) run the changelog phase auto-accepts the
suggested version and the entry preview, whatever the run's autonomy. The phase-runner has no
AskUserQuestion, and the release PR stays open (it is not auto-merged). This is a documented change for
guided driven runs, which used to be asked.
