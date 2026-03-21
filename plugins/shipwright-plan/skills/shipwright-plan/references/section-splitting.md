# Section Splitting

## Purpose

Split the plan into self-contained section files that /shipwright-build can execute independently.

## Approach

### Direct Writing (1-2 sections)
Write section files directly without subagents.

### Batch via Subagents (3+ sections)
Use the `shipwright-plan:section-writer` subagent for parallel generation:

```bash
uv run {plugin_root}/scripts/checks/generate-batch-tasks.py \
  --planning-dir "{planning_dir}"
```

This generates task prompts for each section. The section-writer subagent
receives the plan + section name and writes the section content.

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

## SubagentStop Hook

The `write-section-on-stop.py` hook fires when a section-writer stops.
It reads the subagent's JSONL transcript and extracts the section content.

**CRITICAL — JSONL Race Condition (v0.3.1 fix):**
Claude Code may not flush the JSONL transcript before the hook fires.
The hook retries with exponential backoff: 50ms → 100ms → 200ms.
