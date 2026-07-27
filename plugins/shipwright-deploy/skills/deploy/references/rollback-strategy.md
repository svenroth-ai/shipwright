# Rollback Strategy

> **Jelastic Reference Implementation.** Universal rollback patterns
> (revertable / provenance / procedure) applicable to any deploy target are
> documented in [rollback-discipline.md](rollback-discipline.md). The
> declarative profile is at
> [`shared/profiles/deploy/jelastic.json`](../../../../../shared/profiles/deploy/jelastic.json).
> This file describes the **Jelastic-specific** DEV-vs-PROD rollback procedure.

## DEV Rollback

**Strategy:** Git-based

`VCS.Update` takes **no ref of its own** — it redeploys whatever the VCS
*project* is currently pointed at. So a rollback that only calls Update
redeploys the branch head, which after a bad release is still the bad code.
The ref has to be pinned onto the project first:

1. Identify the last known-good tag/commit.
2. Check whether stored data has moved past it (see below). Refuse if it has.
3. `VCS.GetProjects` — read the current project config for the context.
4. `VCS.EditProject` — send that config back with **only** `branch` replaced.
   A sparse write risks clearing the repository URL and credentials, so the
   full object goes back.
5. `VCS.Update` — deploy the now-pinned ref.
6. `VCS.GetProjects` again — confirm the ref actually took.
7. Verify with the smoke test.

**Automatic:** triggered on smoke test failure after DEV deploy.

```bash
uv run "{plugin_root}/scripts/lib/rollback.py" \
  --env-name "{env_name}" --strategy git --target-ref "{last_known_good_tag}" \
  --project-root . --profile "{shared_root}/profiles/deploy/jelastic.json"
```

### What the result means

| Field | Meaning |
|---|---|
| `ref_verified: confirmed` | the target read back the requested ref |
| `ref_verified: unconfirmed` | pin + update accepted, read-back unavailable (`verification_error` says why). Success, but the message says it is unconfirmed — verify before trusting it |
| `ref_verified: mismatch` | the pin was accepted and did not take — a failure |
| `mutated: false`, exit `1` | refused before contacting the host; nothing there changed |
| `halt: true`, exit `3` | started and did not finish — **stop**, `operator_message` names the state |

### Stored data that has already moved on

Rolling code back does not roll data back. Before any hosting call, the rollback
compares the migrations in the working tree against the target ref; if
migrations exist that the older code does not know, it **refuses** and names
both the migrations and the profile's `data_rollback_strategy`. Untracked
migration files count. A ref git cannot resolve is treated the same way —
being unable to answer is not permission to proceed. `--ack-data-drift`
overrides once someone has decided what happens to the data.

> **Verification status.** `VCS.EditProject` / `VCS.GetProjects` are documented
> in the profile's `known_gaps` as not yet exercised against a live Infomaniak
> environment. The client raises on any non-zero API result, so a wrong endpoint
> surfaces as a reported failure, never as a false success.

## PROD Rollback

**Strategy:** Clone-based
1. Before every PROD deploy: `CloneEnv` creates a backup
2. If smoke test fails: swap to backup clone
3. Backup clone is named `{env}-backup`

**Manual:** User can invoke `/shipwright-deploy --rollback` to:
1. List available backup clones
2. Select one to restore
3. Confirm before proceeding

## Rollback Logging

Every rollback is logged in `.shipwright/agent_docs/decision_log.md`:
```
- **Decision:** Rollback triggered for {env}
  **Rationale:** Smoke test failed: {error}
  **Category:** deployment
```

## Cleanup

Old backup clones should be cleaned up periodically.
The deploy skill keeps only the most recent backup clone.
