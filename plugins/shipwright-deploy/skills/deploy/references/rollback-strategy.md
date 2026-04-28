# Rollback Strategy

## DEV Rollback

**Strategy:** Git-based
1. Identify last known-good tag/commit
2. Call `VCS.Update` with that reference
3. Verify with smoke test

**Automatic:** Triggered on smoke test failure after DEV deploy.

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
