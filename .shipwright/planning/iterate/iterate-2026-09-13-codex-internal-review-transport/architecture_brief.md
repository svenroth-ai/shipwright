# Architecture Brief: Codex internal-review-cascade transport

## Problem
When Codex CLI drives a Shipwright session, its internal review steps
(spec-reviewer/code-reviewer/doubt-reviewer, and plan_review) have no real
mechanism today — only prose in AGENTS.md ("use gpt-5.6-sol for reviews").
Codex CLI has no Agent-tool-equivalent subagent-spawn primitive, so it cannot
literally "spawn a subagent on a different model" the way Claude Code can.

## Options considered

**Option A — a new `"codex"` ModelConfig tier (review/plan_review roles only)
that dispatches to a new subprocess transport.** A separate `codex exec -m
gpt-5.6-sol --sandbox read-only --cd <real worktree> --output-schema <role
schema>` call per review role, mirroring the already-shipped `review_codex()`
external-review leg but with real worktree read access instead of scratch-dir
isolation. Additive: nothing changes for a Claude-driven session.

**Option B — do nothing; keep AGENTS.md prose as the only mechanism.** Costs
nothing to build, but the prose has no enforcement: a Codex-driven session
that skips the model-switch prompt silently gets the same model for build and
review (no independent second opinion), and nothing detects it.

**Option C — build the full alternate-harness spec's `.codex/agents/*.toml`
role-manifest mechanism first, then a generic subagent-model-pinning system,
then wire review through it.** Solves the same problem via a different,
much larger primitive (Codex-native config-based subagent pinning) that does
not exist yet and is unverified — a separate, months-larger effort per
`Spec/codex-runtime-integration-spec.md`.

## What is NOT being decided here
Whether to ever build the full alternate-harness (Option C) — out of scope,
unaffected either way.
