# Section Writer Prompt

You are writing implementation section **{SECTION_NAME}** from the plan.

Read the full plan at: `{PLAN_PATH}`

Your output should be a complete, self-contained section that /shipwright-build
can execute independently. Follow this structure:

## Required Structure

```markdown
# Section: {SECTION_NAME}

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

## Guidelines
- Be specific about file paths and names
- Tests before implementation (TDD)
- Include error handling
- Don't write actual code — describe what to implement
