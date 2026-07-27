# Section Writer Prompt

You are writing implementation section **{SECTION_NAME}** from the plan.

Read the full plan at: `{PLAN_PATH}`

Your output should be a complete, self-contained section that /shipwright-build
can execute independently. Follow this structure:

## Required Structure

```markdown
# Section: {SECTION_NAME}

Requirements: FR-XX.YY, FR-XX.ZZ

## Overview
What this section implements and its role in the larger project.

## Prerequisites
- Dependencies on other sections
- Required packages
- Environment variables

## Tests First
What tests to write BEFORE implementation:
1. Test files and locations
2. Key test cases
3. Edge cases

## Implementation Steps
Ordered steps:
1. ...
2. ...

## Files to Create/Modify
- `path/to/file` — Description

## Verification
- [ ] All tests pass
- [ ] Feature works end-to-end
```

## Required, and checked

These four are gated — `check-plan-gates.py --gate sections` and the plan
phase verifier both fail without them:

1. **`Requirements:`** — a single line naming the requirement ids from the
   spec that this section serves. At least one, and each must be a live id
   from this split's `spec.md`. This is the only place linkage is read from;
   naming an FR in prose does not count. If you cannot name a requirement this
   section serves, the section should not exist.
2. **`## Overview`** — non-empty.
3. **`## Implementation Steps`** — at least two steps.
4. **`## Tests First`** — non-empty.

## Guidelines
- Be specific about file paths and names
- Tests before implementation (TDD)
- Include error handling
- Don't write actual code — describe what to implement
- Under `## Prerequisites`, list what a builder needs to know. Cross-section
  ordering is declared separately in the plan's `SECTION_MANIFEST`
  (`03-api: 01-auth`) and may only name sections of this same plan.
