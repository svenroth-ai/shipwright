# Scope Flows

## Full Application

New project from scratch.

```
User description
  → /shipwright-project (deep interview, multi-split)
    → For each split:
      → /shipwright-plan (research, interview, external review)
        → For each section:
          → /shipwright-build (TDD, code review, commit)
      → /shipwright-test (unit + smoke + E2E)
      → /shipwright-deploy (DEV)
  → /shipwright-changelog (version + PR)
```

**Characteristics:**
- Deep interview (5-15 questions)
- Multiple splits possible
- CLAUDE.md + .shipwright/agent_docs generated
- Full test suite

## Extension

Adding features to existing project.

```
User description
  → /shipwright-project (light interview, usually 1 split)
    → /shipwright-plan (1 spec → sections)
      → For each section:
        → /shipwright-build (TDD, code review, commit)
    → /shipwright-test (unit + smoke + E2E)
    → /shipwright-deploy (DEV)
  → /shipwright-changelog (version + PR)
```

**Characteristics:**
- Reads existing CLAUDE.md + .shipwright/agent_docs
- Light interview (1-3 questions)
- Usually single split
- Existing test suite extended

## Iteration

**Iteration is not a `/shipwright-run` scope.** For quick changes to an
existing project, use the dedicated `/shipwright-iterate` skill, which
has its own complexity-adaptive SDLC (trivial / small / medium / large)
and does not route through the orchestrator at all.

```
/shipwright-iterate "Add dark mode toggle"
```

See `plugins/shipwright-iterate/skills/iterate/SKILL.md` for the full
flow. The `--iterate` flag on `/shipwright-run` and `inference.py` is
deprecated and accepted only for backward compatibility — it does not
change scope detection (existing projects resolve to `extension`).
