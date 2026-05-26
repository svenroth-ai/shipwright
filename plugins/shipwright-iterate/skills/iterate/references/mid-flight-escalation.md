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
