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
- CLAUDE.md + agent_docs generated
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
- Reads existing CLAUDE.md + agent_docs
- Light interview (1-3 questions)
- Usually single split
- Existing test suite extended

## Iteration (`--iterate`)

Quick change to existing project.

```
User description
  → /shipwright-project (1-2 questions, 1 split)
    → /shipwright-plan (1 spec → 1-2 sections)
      → /shipwright-build (implement)
    → /shipwright-test
    → /shipwright-deploy (DEV)
  → /shipwright-changelog
```

**Characteristics:**
- Skips full interview
- Reuses existing config
- 1 split, 1-2 sections
- Fastest path through the pipeline
