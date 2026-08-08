# Per-role model tiers for spawned subagents, resolved by flag > project config > unset

- **Run-ID:** iterate-2026-08-07-agent-model-tiers
- **Spec:** `.shipwright/planning/iterate/2026-08-07-agent-model-tiers.md`
- **Mini-plan:** `.shipwright/planning/iterate/2026-08-07-agent-model-tiers-miniplan.md`

## Context

Every agent definition carries `model: inherit`, so a subagent always runs on
whatever the main session runs on. When the operator drops the session to a
cheaper tier for cost, the review cascade (`spec-reviewer`, `code-reviewer`,
`doubt-reviewer`) and the two unattended finalization drivers
(`section-builder`, `sub-iterate-runner`) follow silently. The run still
reports passed reviews, with no record of which tier produced them. The
defect named in the brief is the silence, not the tier itself.

## Decision

Add an optional `shipwright_model_config.json` (three roles: `review` /
`finalization` / `execution`) plus a per-invocation flag on iterate/build,
resolved with precedence **flag > project config > unset**. Unset (or the
explicit literal `inherit`) omits the Agent tool's `model` parameter entirely
— bit-identical to today's behavior. A shared resolver CLI
(`resolve_model_tier.py`) is called once per run and threaded through every
in-scope spawn site in both skill trees, including the campaign-delegated
ones. `record_review_pass.py` gains an optional `--model-tier`, so
`reviews.json` can carry the tier a pass actually reports having run on — a
self-report, not independently verified provenance, disclosed as such in
`make_entry`'s docstring and spec AC-6. A new F11 predicate
(`review_record_model_tier.py::model_tier_note`) advisory-flags (never
blocks) a completed review pass with no recorded tier, an `inherit` tier, or
a tier below an optional configured floor.

## Rejected alternatives

**Hardcoding `model: opus` / `model: sonnet` in agent frontmatter.** A first
attempt at exactly this was built and abandoned before delivery: pinning
forecloses the operator's own choice in either direction (a shipped default
that pins can't be un-pinned without editing the plugin itself). See
`feedback_shipped_defaults_must_not_take_consumer_freedom` — the fix has to
restore invisibility, not relocate the coercion.

**A single flat `--agent-model` flag / `SHIPWRIGHT_REVIEW_MODEL` env var for
all roles**, proposed independently by both external reviewers on the
`--mode architecture` call (deepseek, openai; both verdict `revise`). Already
considered and rejected in the mini-plan's own "Alternative approach"
section: the operator's stated requirement is to move `review` independently
of `finalization`/`execution` (e.g. keep the review cascade on a strong tier
while dropping the unattended finalization drivers) — a flat single value
forces every role to move together, reproducing the same "one tier for
everything" tradeoff the frontmatter-pin rejection above already ruled out,
just moved from static YAML to a slightly more dynamic flag/env var. The
brief's own "ROLES." section had already settled the three-way split as
non-negotiable for this run, so this was integrated as a reconciled
disagreement (per iteration-planning.md's "'revise' is not a stop") rather
than re-opened.

## Consequences

Additive-only: no agent frontmatter file changes `model:` (11 files,
drift-tested); an unconfigured run is byte-identical to pre-change behavior.
A configured run gets independent per-role control and an honest,
non-blocking record of what each review pass reports having run on, with the
self-report limitation stated in-repo rather than implied as verified.
