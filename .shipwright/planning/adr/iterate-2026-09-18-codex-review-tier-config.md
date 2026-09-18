# A configurable Codex reviewer-identity axis, superseding AC2's static lock; `fable` added to the Claude tier set

**Run ID:** iterate-2026-09-18-codex-review-tier-config
**Full spec:** [`../iterate/2026-09-18-codex-review-tier-config.md`](../iterate/2026-09-18-codex-review-tier-config.md)
**Mini-plan:** [`../iterate/2026-09-18-codex-review-tier-config-miniplan.md`](../iterate/2026-09-18-codex-review-tier-config-miniplan.md)

## Context

Two independent gaps existed in the review-model story:

1. **Claude side:** `lib.model_tier_config.TIERS` enumerated
   `{opus, sonnet, haiku, inherit}` — `fable` (a real, documented Claude Code
   model alias) was missing purely because the set was hand-maintained and
   never updated, not by design.
2. **Codex side:** `lib.codex_review_transport.CODEX_REVIEW_MODEL` was a
   single hardcoded constant (`gpt-5.6-sol`), with no project-config or
   per-run override at all. This was deliberate at the time: iterate-2026-09-13's
   AC2 REMOVED a `model=` override on `run_codex_review` (external-review
   MEDIUM, 2026-09-17) because a public override nothing called was a soft
   convention, not the raise-before-launch lock AC2 required — removing an
   unused knob closed the gap instead of hardening it. But it left the
   Codex-CLI-driven review cascade with no configuration story symmetric to
   Claude's `shipwright_model_config.json` roles at all.

## Decision

**Claude axis:** add `"fable"` to `TIERS`. Deliberately NOT added to
`RANKED_TIERS`/`RANK` — no capability ordering relative to opus/sonnet/haiku
has been established for it, so `fable` gets `inherit`-style floor handling
(unrankable, not "below floor").

**Codex axis (new):** two optional `shipwright_model_config.json` keys,
`codex_review` and `codex_plan_review` (a Codex model slug string, e.g.
`gpt-5.6-terra`), read through the same `lib.model_tier_config` reader as the
Claude roles (one config reader, not two). `run_codex_review` regains a
`model: str | None = None` keyword argument — this time WITH the
raise-before-launch lock AC2 asked for: a new unconditional syntactic
allowlist (`_CODEX_MODEL_SLUG_PATTERN`) rejects a hostile value with
`CodexReviewTransportError` before anything is launched. `review_via_codex.py`
gets a `--codex-model` CLI flag (distinctly named — never reuses
`--review-model`/`--plan-review-model`, which stay Claude-tier-literal-only).
Precedence: `--codex-model` > `shipwright_model_config.json` > the hardcoded
`gpt-5.6-sol` default. Every `run_codex_review` result — `completed` or
`error` — now carries the effective model under `"model"`, and the dispatch
doc requires `--transport-note "<model>"` alongside `--transport codex` so a
configured override is visible in the evidence, not just in config.

**No live Codex model-catalog validation** (see "Rejected alternatives" —
this was the original design, dropped after architecture review).

## Consequences

`gpt-5.6-sol` remains the byte-identical default for every project that does
not opt in — zero behavior change for the unconfigured case. A project that
DOES configure `codex_review`/`codex_plan_review` gets a used, allowlisted,
evidenced override — a stronger posture than AC2's unused static lock, because
this one is load-bearing (config axis) rather than a dead parameter nothing
called. `fable` is now usable across every existing `--review-model`/
`--finalization-model`/`--plan-review-model` flag and config key without
further wiring; six hand-written enumeration sites (`resolve_model_tier.py`,
`review_record_core.py`, `external_review_routing.py`, both `SKILL.md` usage
lines, `docs/guide.md` Appendix B) were updated in the same diff and are now
drift-tested (`test_tier_literal_drift.py`) against a stable literal, so a
future tier addition that forgets one of them fails with a precise
file:string diff instead of silently documenting a stale set.

**Supersedes AC2** (iterate-2026-09-13-codex-internal-review-transport): AC2's
finding was correct for what existed at the time — an override nothing called
was worse than no override. This run's override is called (by
`review_via_codex.py`'s own precedence resolution) and is guarded by the same
kind of hard validation AC2 asked for, so the two decisions are not in
tension — the second one just has a real caller.

**Disclosed residual gap (external code review, MEDIUM, glm, 2026-09-18):**
AC35's audit trail — `--transport-note` naming the effective model on a
`--transport codex` review row — is enforced only by the dispatch-doc prose
(`shared/prompts/codex_review_dispatch.md`), never by `record_review_pass.py`
itself. A dispatching agent that skips that documented flag loses the
evidence silently; the code change here (`run_codex_review` returning the
effective model) makes the value available, it does not force it to be
recorded. Closing this in code would require `record_review_pass.py` to
accept the transport's own result JSON (not just the reviewer's canonical
payload file it already reads), which is a wider change to a tool every
review type dispatches through — out of proportion to this iterate's scope.
Accepted as a known limitation, same class as this repo's other
prose-enforced review-recording mandates (see
`references/iteration-reviews.md`'s "Immediate-write ordering mandate: this
is a mitigation, not a guarantee").

**Revert is noisy, not silent (doubt-reviewer LOW, 2026-09-18):** once a
project's `shipwright_model_config.json` gains a `codex_review`/
`codex_plan_review` key, reverting this diff removes `CODEX_KEYS` from
`load_model_config`'s unknown-key allowlist, so every subsequent config read
(on paths unrelated to Codex — every iterate's tier resolution, every F11
floor check) emits an "unrecognized key" warning until the key is removed by
hand. Fail-soft, never fail-dangerous, and accepted — the config surface is
forward-but-not-backward compatible by design, same as any additive schema
key.

## Rejected alternatives

- **Live Codex model-catalog validation** (`codex debug models`, memoized,
  fail-closed on catalog-unreachable) — this was the ORIGINAL chosen design
  for the Codex axis, built into a full mini-plan (`codex_model_catalog.py`,
  a cache, a two-stage fail-open/fail-closed policy) before Architecture
  Review. **Rejected** after both external reviewers (openai=reject,
  glm=revise/high) converged: the check buys "an invalid model is caught
  slightly earlier" at the cost of a standing dependency on an undocumented
  CLI subcommand whose shape had already changed mid-session (codex-cli
  0.147.0 → 0.155.0 added a fifth model, `gpt-6-astra`) — the exact
  instability that motivated building the check is also evidence the check
  itself is the less stable of the two things it compares. Its fail-closed
  policy also made an explicitly configured run MORE fragile to transient
  CLI/network flake than an unconfigured run — a perverse incentive against
  using the feature. What remains (config axis + syntactic allowlist +
  Codex's own launch error as the semantic check) is what glm separately
  confirmed as "the smallest thing that would do."
- **Folding Codex identities into `TIERS` as new literals** (e.g.
  `"gpt-5.6-sol"` as a `TIERS` member) — rejected: `TIERS` is a closed,
  hand-maintained enum by design, mirroring the Agent tool's own closed
  `model` parameter schema (confirmed empirically: `{sonnet, opus, haiku,
  fable}`, no live introspection API). Codex's model space is open-ended and
  introspectable (`codex debug models`); forcing it through the same closed
  gate would either freeze Codex's list too (reintroducing this iterate's
  own motivating staleness bug) or silently loosen the Claude-side check.
  Keeping the two axes structurally separate (closed enum vs.
  allowlist-then-Codex-validated string) maps each axis's real integrity
  boundary correctly.
- **A "codex" literal usable regardless of which harness drives** — an early
  framing error, corrected by Sven directly: Claude always reviews on Opus
  and Codex always reviews on the configured Codex identity — the two axes
  are resolved independently by which harness is actually driving, never a
  single shared literal.
- **Live model-catalog discovery for BOTH axes** (Claude included) — explored
  per Sven's request, then dropped for the Claude side specifically: the
  Agent tool's `model` parameter is a harness-level fixed enum with no
  external introspection surface at all (unlike Codex's own CLI), so "live"
  discovery is architecturally impossible there; the Claude-side fix is
  correcting the hardcoded list (adding `fable`), not building a discovery
  mechanism with nothing to discover from.
- **Escalating this run to `large` complexity** (a full separate pipeline
  hand-off) — rejected per Sven's explicit call to stay at `medium`; the
  iterate skill's own mid-flight-escalation tooling (mini-plan + external
  plan review + architecture review) was exactly what was needed to resolve
  the two open design questions, and did so without a pipeline hand-off.

See the full iterate spec's `## Acceptance Criteria`, `## External Plan
Review`, and `## Architecture Review` sections for the complete review
history and finding-by-finding dispositions.
