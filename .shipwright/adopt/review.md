# Adoption Review — Skipped

**Date:** 2026-05-02
**Project:** shipwright (self-adoption of the framework monorepo)
**Profile:** python-plugin-monorepo
**Scope:** library

## Layer-3 review status

**Skipped: review-not-applicable-for-self-adoption**

The Layer-3 review step is intended to surface inconsistencies when adopt
runs on a brownfield repository written by a different team. For the
shipwright monorepo's self-adoption, this is the team that wrote the
framework adopting their own code; the artifacts in
`.shipwright/agent_docs/`, `.shipwright/planning/01-adopted/spec.md`, and
the retroactive ADRs in `.shipwright/agent_docs/decision_log.md` are
expected to match the team's mental model by construction.

## Plan-level external review (substituting for Layer-3)

The adoption plan itself was reviewed by Gemini + GPT in parallel via
OpenRouter (`shared/scripts/tools/external_review.py --mode plan`)
before this run. Findings are in
`~/.claude/plans/du-hast-ein-memory-magical-hippo.review.json` and the
External-Review-Trace table at the end of
`~/.claude/plans/du-hast-ein-memory-magical-hippo.md`. All NO-GO
findings were addressed in plan v3 before adoption.

## Empirically verified prerequisites

- `validate_adoption.py:24-30` REQUIRED_CONFIGS: 5 (run, project, plan,
  build, compliance) — all written
- `validate_adoption.py:72` FR-NN.MM tag in spec.md: enforced; FRs
  numbered automatically as FR-01.NN by
  `generate_adoption_artifacts.py:321-322`
- CLAUDE.md byte-for-byte preservation verified via SHA256 baseline
  before and after the adopt run

## Follow-ups (not blocking adoption)

- `validate_adoption.py:_count_adrs` regex was missing H3 support
  (drift vs. commit 63352ff which switched ADR canonical form to H3);
  fixed in this iterate.
- A handful of TODO/FIXME/HACK markers were inventoried in
  `.shipwright/agent_docs/known_issues.md` — these are existing tech
  debt, not adoption issues.
