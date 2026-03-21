# Section Documentation Updates

## Decision Log

After code review interview, write decisions to `agent_docs/decision_log.md`:

```bash
uv run {plugin_root}/scripts/tools/write_decision_log.py \
  --project-root "$(pwd)" \
  --section "{section_name}" \
  --decisions '[{"decision": "Use Zustand over Context", "reason": "Simpler API, better devtools", "category": "architecture"}]'
```

### What to Log
- Architecture choices (state management, data flow, patterns)
- Review findings: accepted/declined with reasoning
- Spec deviations and why
- Performance tradeoffs made

### What NOT to Log
- Trivial implementation details
- Standard framework usage
- Obvious choices

## Session Handoff

Before context limits, generate handoff:

```bash
uv run {plugin_root}/scripts/tools/generate_session_handoff.py \
  --project-root "$(pwd)" \
  --section "{section_name}" \
  --status "{complete|in_progress}"
```

This writes `agent_docs/session_handoff.md` with:
- Current section and status
- What's been done
- What's remaining
- Open questions or blockers
