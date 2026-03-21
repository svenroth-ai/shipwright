# Code Review Protocol

## Overview

After implementation, spawn the code-reviewer subagent to review the diff
against the section spec. The reviewer checks for bugs, security issues,
performance problems, and spec compliance.

## Steps

1. Generate diff:
```bash
git diff HEAD > /tmp/shipwright-review-diff.txt
```

2. Spawn `code-reviewer` subagent with:
   - Section spec file path
   - Diff file path

3. Receive structured review:
```json
{
  "section": "01-auth",
  "review": [
    {
      "severity": "high|medium|low",
      "category": "bug|security|performance|style|spec-gap",
      "file": "src/auth/login.ts",
      "line": 42,
      "finding": "Description",
      "suggestion": "How to fix"
    }
  ]
}
```

## Handling Results

- **high severity**: Must fix before commit
- **medium severity**: Present to user, fix if accepted
- **low severity**: Log and optionally fix

## No Findings

If review returns no findings, proceed to commit.
