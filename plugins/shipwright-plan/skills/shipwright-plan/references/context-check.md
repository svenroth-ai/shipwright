# Context Window Management

## Purpose

Before writing the plan (a large artifact), check if context is getting large.
If so, summarize what we know before proceeding.

## When to Check

- After research + interview, before plan writing
- After external review, before section splitting
- Any time the conversation has had 20+ tool calls

## Script

```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/check-context-decision.py
```

The script doesn't measure actual context — it prompts Claude to self-assess.

## If Context is Large

1. Write a brief outline (5-10 bullet points) for user approval
2. Suggest `/clear` if context is very large
3. Session state ensures seamless resume after clear
