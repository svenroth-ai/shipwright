# Autonomy Levels

## Guided (default)

Interactive process through all phases including Build and Test,
with confirmation between phases and request for approval of fixes.

- **Between phases:** Orchestrator asks "Continue to next phase?"
- **Build:** Code review findings presented via AskUserQuestion (Accept/Decline/Defer per finding)
- **Test:** Failures reported. Auto-fix only with explicit --fix flag.

## Autonomous

Interactive process through Spec and Design with autonomous Build and Test
including fixes. Deploy stays interactive.

- **Spec & Design:** Same as Guided — user input shapes architecture
- **Between phases:** Orchestrator proceeds without asking
- **Build:** Code review findings are auto-fixed immediately. All findings treated as accepted.
  Fixes logged in decision log.
- **Test:** Failures trigger auto-fix automatically (structured debugging, up to 3 retries).
  No --fix flag needed.
- **Deploy:** Same as Guided — PROD confirmation always required

**Always interactive regardless of level:**
- Destructive database operations (always require confirmation)
- Rollback decisions (always require confirmation)

## Configuration

Set in `shipwright_run_config.json`:
```json
{
  "autonomy": "guided"
}
```

Per-invocation:
```
/shipwright-run --autonomous "Build a todo app"
```
