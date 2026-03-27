# Autonomy Levels

## Guided (default)

The orchestrator asks the user at key decision points:

1. **After inference:** "Settings look correct?"
2. **After project phase:** "N splits created. Continue to design?"
3. **After design phase:** "UI mockups created. Continue to planning?"
4. **After plan phase:** "M sections planned. Start building?"
5. **After build phase:** "All tests pass. Deploy to DEV?"
6. **After deploy:** "Smoke test passed. Create changelog + PR?"

**Always asks regardless of level:**
- PROD deployment confirmation
- Destructive database operations (DROP TABLE, etc.)
- Rollback decisions

## Autonomous

The orchestrator proceeds without asking, except for the "always ask" items above.

Suitable for:
- Iteration mode (small, well-understood changes)
- CI/CD integration (future)
- Experienced users who trust the pipeline

## Configuration

Set in `shipwright_run_config.json`:
```json
{
  "autonomy": "guided"  // or "autonomous"
}
```

Can also be set per-invocation:
```
/shipwright-run --autonomous "Build a todo app"
```
