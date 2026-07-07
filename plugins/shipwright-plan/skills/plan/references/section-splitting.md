# Section Splitting

## Purpose

Split the plan into self-contained section files that /shipwright-build can execute independently.

## Approach

### Direct Writing (1-2 sections)
Write section files directly without subagents.

### Batch via Subagents (3+ sections)
Use the `shipwright-plan:section-writer` subagent for parallel generation:

```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/generate-batch-tasks.py \
  --planning-dir "{planning_dir}"
```

This generates task prompts for each section. The section-writer subagent
receives the plan + section name and **writes the section file to disk itself**
(it has a Write tool) at `{planning_dir}/sections/{NN-name}.md`.

## Section File Structure

Each section file should be self-contained for /shipwright-build:

```markdown
# Section: 01-auth

## Overview
What this section implements.

## Prerequisites
- Dependencies on other sections
- Required packages

## Tests First
1. Test file: `tests/auth.test.ts`
2. Key assertions: ...

## Implementation Steps
1. Create data model
2. Implement API routes
3. Build UI components

## Verification
How to verify this section is complete.
```

## SubagentStop Hook (non-blocking fallback)

The section-writer persists its own file (it has a Write tool). The
`write-section-on-stop.py` hook is a **defensive fallback** that fires when a
section-writer stops:

- if the section file already exists on disk (the direct write) → **no-op
  success**; it never blocks and never clobbers;
- if the file is missing → it best-effort **salvages** the content from the
  subagent JSONL transcript and writes it;
- if it cannot salvage → it logs to stderr and exits 0. **It never blocks** —
  Step 7 (`check-sections.py`) is the gate for a missing section. (Supersedes
  the ADR-042 block-on-failure behavior; a blocking fallback would false-block a
  successful direct write.)

**CRITICAL — JSONL Race Condition (v0.3.1 fix):** the salvage path may fire
before Claude Code flushes the JSONL transcript, so it retries with exponential
backoff: 50ms → 100ms → 200ms.
