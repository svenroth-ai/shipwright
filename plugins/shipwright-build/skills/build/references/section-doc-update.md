# Section Documentation Updates

## Decision Log

After code review interview, write each decision to `agent_docs/decision_log.md` using the shared ADR tool (one call per decision):

```bash
uv run {plugin_root}/../../shared/scripts/tools/write_decision_log.py \
  --section "Build — {section_name}" \
  --commit "$(git rev-parse HEAD)" \
  --context "Needed simpler state management with better devtools" \
  --decision "Use Zustand over Context API" \
  --consequences "Less boilerplate, no provider nesting" \
  --rejected "Redux, React Context" \
  --project-root "$(pwd)"
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
uv run {shared_root}/scripts/tools/generate_session_handoff.py \
  --project-root "$(pwd)" \
  --reason "mid-build handoff: section {section_name}"
```

This writes `agent_docs/session_handoff.md`. The shared handoff writer
reads `shipwright_build_config.json` automatically, so the current
split, current section, completion counts, last events, and recent
ADRs all get populated from the persisted state — no extra flags
needed. The `--reason` string becomes the header line so the next
session understands at a glance why the handoff was written.
