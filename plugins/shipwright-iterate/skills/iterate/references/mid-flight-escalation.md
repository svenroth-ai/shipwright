# Mid-Flight Escalation

The agent can upgrade complexity mid-flight if scope is expanding.

## Escalation rules

- **trivial → small:** Add self-review (if not running), widen test scope.
- **small → medium:** Backfill in order:
  1. Create iterate spec retroactively
  2. Create mini-plan (document what was done + what remains)
  3. Run external LLM review BEFORE further code changes
  4. Continue at medium level
- **any → large:** Differentiated by state:

| When detected | State | Action |
|---|---|---|
| During Repo Scout / Planning | Clean | Clean transition → escape hatch |
| During Build | Dirty (code partially written) | WIP checkpoint commit, then escape hatch with user choice: revert + pipeline, or continue |
| During Test | Dirty (tests failing) | Same as build, handoff notes test failures |

See `references/iteration-planning.md` for escape hatch protocol.

## Implementation

After build and after test, check: "Did actual scope exceed estimated
complexity?" If yes, upgrade.

## Integrate origin/main (stale-PR reconciliation)

When `origin/main` advances while this iterate's PR is open, the PR goes
`CONFLICTING` / `DIRTY`. The conflicts are **only** on generated/"churn"
artifacts (`shipwright_events.jsonl`, the compliance + agent-doc MDs,
`shipwright_test_results.json`) — never real source. **Do NOT hand-resolve them
and do NOT run a bare `git merge origin/main`.** Run the wrapper:

```bash
uv run "{shared_root}/scripts/tools/integrate_main.py" \
  --project-root . --run-id "<run_id>"
```

It fetches, merges `origin/<default>`, reconciles churn conflicts via
`resolve_churn_conflicts.py` (events → `merge=union` + validate; derived MDs →
regenerate from the merged tree; `test_results.json` → ours), commits the merge,
then commits the regenerated MD snapshots as a **separate, non-merge follow-up
commit** carrying the `Run-ID:` trailer (required — `audit_staleness` skips merge
commits). **Hard safety gate:** if ANY non-churn (source) file conflicts, the
wrapper aborts the merge untouched and exits non-zero — resolve those by hand,
then re-run. See `docs/hooks-and-pipeline.md` → "Merge reconciliation of churn
artifacts" for the full strategy table and rationale.
