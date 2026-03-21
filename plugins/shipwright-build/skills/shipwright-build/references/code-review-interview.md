# Code Review Interview

## When Triggered

After code-reviewer subagent returns findings with medium+ severity.

## User Interaction

Present each finding via AskUserQuestion:

```
Code Review Finding ({severity}):
  File: {file}:{line}
  Issue: {finding}
  Suggestion: {suggestion}

How would you like to handle this?
  - Accept: Fix the issue
  - Decline: Skip (will log reason in decision log)
  - Defer: Add TODO comment for later
```

## Triage Rules

- Group related findings together
- Present high severity first
- For low severity: batch present ("3 style suggestions — accept all?")

## After Triage

For each accepted finding: apply fix, run tests.
For each declined finding: log reason in decision log.
For each deferred finding: add `// TODO(shipwright): {finding}` comment.
