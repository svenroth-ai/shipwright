# Iterate spec brief (small, spec_impact none)
Run: iterate-2026-11-21-gpt-6-2-sol-bump
Goal: bump the OpenAI review reviewer identity from GPT-6.1 Sol to GPT-6.2 Sol everywhere it is used for internal + external review and the Codex transport.
AC1: every live reference `gpt-6.1-sol` / `openai/gpt-6.1-sol` / "GPT-6.1 Sol" in config, code, prompts, schema, docs, tests becomes the 6.2 slug (openai/gpt-6.2-sol on OpenRouter, gpt-6.2-sol direct + Codex).
AC2: history (ADRs, CHANGELOG, compliance, triage, events, old iterate artifacts) is NOT rewritten.
AC3: gpt-6-luna and the Haiku PR-review gate are untouched.
AC4: slugs live-verified (OpenRouter model list + codex exec -m gpt-6.2-sol answered OK).
