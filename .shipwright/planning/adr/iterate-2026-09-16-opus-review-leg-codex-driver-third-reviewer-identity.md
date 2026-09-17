# A third, cross-vendor external-reviewer identity ("opus"), gated by a required `--driver` flag

**Run ID:** iterate-2026-09-16-opus-review-leg-codex-driver
**Full spec:** [`../iterate/2026-09-16-opus-review-leg-codex-driver.md`](../iterate/2026-09-16-opus-review-leg-codex-driver.md)
**Mini-plan:** [`../iterate/2026-09-16-opus-review-leg-codex-driver-miniplan.md`](../iterate/2026-09-16-opus-review-leg-codex-driver-miniplan.md)

## Context

`external_review.py`'s roster was hard-coded to `{glm, openai}` regardless of
which harness drove the diff. When a Codex-CLI-driven iterate ran external
review, the "openai" leg (`gpt-5.6-terra`) reviewed code that Codex itself —
the same vendor, frequently the same model — just wrote. That looks identical
to the genuinely independent case where Claude drives and GPT reviews, but is
a vendor-mode self-review.

## Decision

Add a third, Anthropic-backed reviewer leg ("opus": local `claude` CLI
primary transport, OpenRouter `anthropic/claude-opus-5` fallback) and a
required, no-default `--driver {claude,codex}` CLI flag. `--driver claude`
keeps today's `{glm, openai}` roster unchanged; `--driver codex` swaps to
`{glm, opus}`. All 8 real plugin prose call sites were wired to pass the
correct value, enforced by a grep-based drift-protection contract test
(fenced-block AND inline-prose scanning) rather than prose-trust alone.

## Consequences

External review is now provider-independent from whichever CLI authored the
diff, in both directions the framework supports. Every existing
`external_review.py` invocation (docs, tests, prose call sites) needed a
one-line `--driver` addition — a required, no-default flag is a breaking CLI
change by design, not a regression. New marker schema 5 (`{glm, opus}`)
added alongside the existing schema 4, both recognized by every marker
reader in the repo (verified via a repo-wide grep, not just the two writers).

**Known limitation, disclosed and tracked (not silent):** the mechanism
ships without a real caller ever passing `--driver codex` from an actual
Codex-CLI-driven session yet — `AGENTS.md`'s cascade and the iterate skill's
own driver-resolution still need that follow-up wiring, tracked as
`trg-a27ab4d9` (high). The direct `/shipwright-iterate` path resolves
`{driver}` correctly today (the executing harness states its own identity —
iteration-planning.md). The campaign path's `sub-iterate-runner.md` hardcodes
`--driver "claude"` rather than leaving `{driver}` unresolved: that agent is
only ever spawned as a Claude Code subagent (the Agent tool has no Codex-CLI
equivalent yet), so `claude` is the only value that can reach it today —
`trg-a27ab4d9` remains the tracker for wiring a real Codex-driven campaign
once that spawning mechanism exists. On Windows, the npm-installed `claude`
binary is a `.cmd` shim, which this leg deliberately refuses (BatBadBut
hardening) — so `OPENROUTER_API_KEY` becomes load-bearing for every
`driver=codex` run on Windows until/unless a non-shim local Claude CLI
install is used.

## Rationale

The stdin/argv split (untrusted diff/spec text rides stdin only; rendered
instructions become the `-p` argument) mirrors the already-shipped
`review_codex()` leg's isolation posture (`--sandbox read-only`,
`--ignore-user-config`) with a Claude-CLI-equivalent set
(`--strict-mcp-config` + `--allowedTools ""` + `--permission-mode dontAsk`).
Reusing `resolve_reviewer_model`'s identity-lock pattern and
`classify_reply`'s degraded-response handling keeps the new leg consistent
with the two existing ones rather than inventing a fourth pattern.

## Rejected alternatives

- **A default value for `--driver` (e.g. defaulting to `claude`)** — rejected
  per Sven's explicit call: a silent default would let a Codex-driven run
  that forgot the flag silently reintroduce the exact vendor self-review this
  iterate exists to close. Fail-closed (argparse error) beats fail-open.
- **Auto-detecting the driver from the environment** — rejected; Sven chose
  an explicit, required CLI flag over env-var sniffing, per-project config,
  or a default value, to keep driver identity structural rather than
  heuristic.
- **A `review_opus_openrouter()` wrapper function** — dropped; the OpenRouter
  fallback calls the existing `review_openrouter(..., model_key="opus")`
  directly, since wrapping a single parameterized call added no clarity
  (opus-plan-reviewer LOW finding).
- **A generic, pluggable multi-driver "agent system" architecture** —
  rejected as premature over a plain closed `DRIVER_CHOICES = ("claude",
  "codex")` enum, cheap to extend later if a real third driver appears.
- **Literal `--model opus` alias** — rejected in favor of the
  identity-locked, dynamically-resolved pinned model string
  (`claude-opus-5`), for identity-lock symmetry with the OpenRouter leg's
  exact slug.

See the full iterate spec's `## Acceptance Criteria`, `## External Plan
Review`, and `## Architecture Review` sections for the complete review
history and finding-by-finding dispositions.
