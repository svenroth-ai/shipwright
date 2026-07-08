# Single-Session Gate Discipline

**Applies to:** every phase-runner subagent (project / design / plan / build /
deploy) running under the **single-session pipeline**
(`shipwright_run_config.json` `mode: "single_session"`, Campaign 2026-07-07).

**Additive & inert otherwise.** Under `multi_session` (deprecated), standalone,
or any unrecognised mode, this contract does nothing — every gate resolves to
`interactive` and you behave exactly as your phase already documents.

## The rule

Before you STOP at any interactive `AskUserQuestion` gate in your phase, resolve
its policy from the catalog:

```bash
# one gate:
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/resolve_gate_policy.py" \
  --gate <gate-id> --project-root .
# or every gate for your phase, already resolved for the current mode:
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/resolve_gate_policy.py" \
  --phase <phase> --list --project-root .
```

Mode precedence: `--mode` > `$SHIPWRIGHT_RUN_MODE` > `run_config.mode` >
`multi_session`. Apply the printed `effective_policy`:

| `effective_policy` | what you do |
|---|---|
| `interactive` | Behave exactly as documented: call `AskUserQuestion` and STOP. Not a single-session run — the mechanism is inert. |
| `auto-default` | Do **not** call `AskUserQuestion`; do **not** end the turn. Proceed with the printed `default_answer`. |
| `orchestrator-approve` | **Still STOP.** End the turn and return a gate-pending result to the orchestrator to surface to a human — never auto-answer. |
| `hard-stop` | **Still STOP.** An explicit human decision is required regardless of autonomy: PROD deploy, destructive SQL, migration-apply failure, rollback (`shared/constitution.md` ASK FIRST / NEVER). |

## Non-negotiables

- **Never auto-answer an `orchestrator-approve` or `hard-stop` gate.** The
  constitution's "Tool Call Discipline — AskUserQuestion" still governs; these
  gates end the turn.
- **Never fabricate an answer for a gate that is NOT in the catalog.** A decision
  question you don't recognise still routes through `AskUserQuestion`. (The CLI
  also resolves an unknown gate id to `interactive` for exactly this reason.)
- **Fail safe, not fail-blocking.** If the resolver errors or is unavailable
  (missing/corrupt catalog, bad invocation), behave **interactively** — call
  `AskUserQuestion` and STOP, exactly as a `multi_session` run would. Never block
  the run or auto-answer on a resolver failure.
- **`default_answer` is opaque guidance, not a parsed value.** Apply it in
  context; do not build ad-hoc parsing on its exact wording.
- **Constitution lock (SS3+ invariant).** A gate whose resolved result has
  `constitution: true` is NEVER auto-approvable by any autonomy level — even an
  `orchestrator-approve` one always reaches a human. `constitution` is the real
  lock; `policy` only distinguishes "surface to the orchestrator" from "a human
  must decide here, full stop".
- Machine SSoT: `shared/config/gate_catalog.json`. Human reference:
  `docs/gate-catalog.md` (generated from the JSON).
