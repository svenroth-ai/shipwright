# Reflection Protocol

After completing work, reflect on what was learned during implementation.

## Questions to consider

1. **New patterns**: Did you discover a reusable approach, naming convention, or architectural pattern that should be documented?
2. **Gotchas**: Did you encounter unexpected behavior (API quirks, framework limitations, migration pitfalls) that future sessions should know about?
3. **Corrections**: Was an existing convention wrong, incomplete, or misleading? Should it be updated?
4. **Tool/infra insights**: Did you learn something about the build system, deployment, or test infrastructure that isn't documented?

## Actions (only if learnings exist — do not force entries)

### For decisions (pattern chosen, convention corrected)
Use `write_decision_log.py` with `--architecture-impact convention` — creates a proper ADR and auto-appends to conventions.md.

### For observations (gotchas, framework quirks, infra insights)
Append directly to `agent_docs/conventions.md` under `## Learnings`:
```
- ({YYYY-MM-DD}) {phase} — {summary}
```

### For cross-project insights (only in main-conversation Skills, not in subagents)
Save a Claude Code feedback or project memory if the learning applies beyond this project.

If no learnings: skip. Do not create empty or boilerplate entries.
