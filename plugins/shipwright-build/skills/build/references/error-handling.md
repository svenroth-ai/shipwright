# Error Handling

Detail for Kern "Error Handling" section.

## Test Failures

Follow the [debugging-protocol.md](debugging-protocol.md):

1. **Root cause investigation** — read error output, identify failing component
2. **Pattern analysis** — same root cause as last attempt? If yes -> change approach
3. **Hypothesis** — state what you'll fix and why before changing code
4. **Fix and verify** — targeted fix, then re-run tests
5. If stuck after 3 attempts (or 2 with same root cause): escalate to user

## Pre-commit Hook Failures

See [pre-commit-handling.md](pre-commit-handling.md).

- Linting failures: auto-fix and re-commit
- Type errors: fix and re-commit
- Don't bypass hooks with `--no-verify`

## Context Window Pressure

Context pressure is checked automatically at Kern Steps 4 and 8 via `estimate_context_pressure.py`.
If `recommend_checkpoint` is true mid-section:

1. Commit current progress (partial)
2. Generate session handoff
3. Update dashboard with `--status paused`
4. Print checkpoint banner:

```
================================================================================
CHECKPOINT — Context pressure detected
================================================================================
Progress saved. Section {section_name} paused at step {N}.
Dashboard: .shipwright/agent_docs/build_dashboard.md

To continue:
  1. Open a new session (+ button) <- recommended
  2. Or: /clear in this session

Then invoke: /shipwright-run
  -> Auto-resumes from {section_name}
================================================================================
```

5. **STOP** — do not continue.
