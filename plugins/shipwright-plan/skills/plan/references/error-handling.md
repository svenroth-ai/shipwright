# Error Handling

## Missing API Keys

Handled interactively in Step 5 Branch B. If no API key is detected in
`.env.local`, the skill STOPS and asks the user whether to add a key
(Option 1) or opt out into self-review fallback (Option 2). Never
silently skipped.

```
Note (legacy): silent-skip behavior was removed. See Step 5 Branch B for the
current interactive flow.
```

## Section Writer Failure

If a section-writer subagent fails:
1. Log the error
2. Attempt to write the section directly (without subagent)
3. If still fails: mark section as incomplete, continue with others

## Context Window Pressure

If context is getting large during plan writing:
1. Save progress so far
2. Suggest user run `/clear` and resume
3. Session state allows resuming from any step
