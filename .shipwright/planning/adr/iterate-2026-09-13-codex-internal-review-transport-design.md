# Codex CLI as a fallback transport for the internal review cascade

**Run ID:** iterate-2026-09-13-codex-internal-review-transport
**Full spec:** [`../iterate/iterate-2026-09-13-codex-internal-review-transport.md`](../iterate/iterate-2026-09-13-codex-internal-review-transport.md)
**Mini-plan:** [`../iterate/iterate-2026-09-13-codex-internal-review-transport-MINIPLAN.md`](../iterate/iterate-2026-09-13-codex-internal-review-transport-MINIPLAN.md)

## Context

The internal review cascade (spec-reviewer → code-reviewer → doubt-reviewer,
plus `opus-plan-reviewer`) is spawned via Claude Code's Agent tool, which
assumes the driving harness is Claude Code itself on an Anthropic model. Two
real triggers break that assumption: (1) the driving session is Codex CLI
itself, which has no Agent-tool equivalent, or (2) a Claude Code session has
been redirected to a non-Anthropic backend, so an "independent" Agent-tool
spawn would not actually be model-independent. Either case previously forced
the cascade to silently degrade or record a policy-shaped `not_run`.

## Decision

Add `shared/scripts/lib/codex_review_transport.py` + a CLI wrapper
`shared/scripts/tools/review_via_codex.py` that run `codex exec -m
gpt-5.6-sol` as a real subprocess against the actual worktree, under an
explicit env allowlist (never inherited ambient secrets), `--sandbox
read-only`, with per-role output schemas validated both by `--output-schema`
and a second client-side pass. State a single dispatch rule once at each of
four real orchestrator spawn sites (build Step 6, iterate Step 8, plan Step
5, iterate campaign 3f-bis): before an Agent-tool spawn, check whether this
session can genuinely spawn an independent subagent; if not, run
`review_via_codex.py` for that role instead. `record_review_pass.py` gains
`--transport {agent,codex}` and `--transport-note` to keep a Codex-answered
row evidentially distinguishable from an ordinary one.

## Consequences

Every review role degrades gracefully on preflight or mid-run failure
(non-zero exit, timeout, empty/stale/schema-invalid output) rather than
silently proceeding as reviewed or hard-crashing the run; where a genuine
Agent-tool fallback exists it is used, otherwise the pass is recorded
`not_run` with the concrete failure named. `gpt-5.6-sol` is locked as a
distinct model identity from the external-review leg's `gpt-5.6-terra`. No
`ModelConfig` schema change ships — an earlier design that bumped the schema
and forked review-invocation prose at every "model tier" note was dropped
during Architecture Review as unnecessary surface for a same-repo dispatch
check. Reads from the real worktree (including `.env*`) reach the operator's
own Codex/OpenAI account — a materially different exposure than the flat
diff+spec text the external-review leg isolates to, disclosed and accepted
rather than solved with a path-exclusion allowlist (YAGNI-guarded follow-up,
not built here).

## Rationale

Reuses the existing external-review leg's subprocess isolation posture
(`review_codex()`'s stdin/argv split, scrubbed env) rather than inventing a
second pattern. Evidence parity is achieved without a new `--from
codex-transport` adapter — `record_review_pass.py` keeps its existing
`--from {spec-reviewer,code-reviewer,doubt-reviewer}` values and layers
`--transport`/`--transport-note` on top, because the four existing consumers
(`record_review_pass.py`, `check_review_record`, the WebUI, `doubt-reviewer`)
already parse the exact payload shapes AC4 pins; a new adapter name would
have to parse the same three shapes under a fourth label. The dispatch rule
is stated only at the orchestrator's own spawn sites, never inside a
delegate subagent's own instructions (ADR-029 carve-out) — `sub-iterate-runner`
and build's `section-builder` are never the driving harness and keep
recording the cascade `not_run` exactly as before.

## Rejected Alternatives

- **A `ModelConfig` schema bump adding a "codex" model tier**, forking
  review-invocation prose at every "model tier" note across four skills —
  dropped during Architecture Review as unstated new surface for what is
  actually a same-repo dispatch condition, not a model-tier choice.
- **A new `--from codex-transport` adapter** in `record_review_pass.py` —
  rejected because it would have to parse three different payload shapes
  under one name when the existing `--from` values already parse them
  identically.
- **Inheriting the ambient process environment** for the `codex` subprocess —
  rejected outright (Internal Plan Review HIGH finding): the ambient env
  carries `OPENROUTER_API_KEY`/`OPENAI_API_KEY`/`GITHUB_TOKEN`/
  `ANTHROPIC_API_KEY` into an agentic, network-capable child process.
- **Sending the reviewer agent's `.md` file verbatim as the prompt** —
  not viable: the file assumes filesystem-write and `behavior_snapshot.py`
  capabilities this transport does not have, so the transport strips
  frontmatter and states what's unavailable instead.
- **Parallel review-role dispatch** — rejected (External Review, glm, LOW):
  a flat-fee ChatGPT/Codex subscription plan has its own concurrency limits,
  so the three roles run sequentially with a budgeted per-role timeout and
  `max_retries=0`.
