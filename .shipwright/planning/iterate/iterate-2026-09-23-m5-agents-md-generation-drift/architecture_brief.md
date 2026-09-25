# Architecture Brief: AGENTS.md generation in adopt + project

## The problem

**Revised after round 1 (openai reject, glm revise): the Claude Code
2.1.277 CLAUDE.md-absent fallback is NOT the load-bearing reason — Shipwright
already writes `CLAUDE.md` unconditionally, so that fallback firing is a
rare, self-inflicted state (the user deleted it). The real reason is
different and does not depend on CLAUDE.md's presence at all: Codex CLI
reads `AGENTS.md` as its OWN, native, first-class convention — not a
fallback. Today neither `/shipwright-adopt` (brownfield) nor
`/shipwright-project` (greenfield) ever writes one, so a Codex session in
ANY Shipwright-managed project gets zero Shipwright guidance, regardless of
whether `CLAUDE.md` exists.**

## What already exists here

- `plugins/shipwright-adopt/scripts/lib/claude_md_renderer.py` — Python
  renderer + writer for `CLAUDE.md`, with load-bearing preservation
  (existing file >1KB kept untouched, suggestion written to a side-file) and
  idempotent append of the review-cascade standing-request section.
- `shared/templates/claude-md-template.md` — the template
  `/shipwright-project` (an LLM agent, not a script) loads and fills for a
  greenfield `CLAUDE.md`.
- A drift test (`test_claude_md_template.py`) already exists because these
  two independent producers previously fell out of sync.
- This same iterate already fixed the analogous drift between THIS
  monorepo's own hand-maintained root `CLAUDE.md`/`AGENTS.md`.

## What would newly, permanently exist

A second generated file (`AGENTS.md`) produced by both pipelines from now
on, sharing `claude-md-template.md`'s existing body verbatim (no second
template, no drift test — there is only one copy of the shared content to
begin with) plus one small, separately-maintained Codex-only appendix file
read identically by both producers at generation time. Adopt also gets a
load-bearing-preservation path for a pre-existing user `AGENTS.md`, matching
its existing `CLAUDE.md` policy (this preserves the user's own file — it
does not resolve a contradiction between it and Shipwright's content; the
mechanism's job is guidance-absence, not contradiction-detection).

## Options on the table

- **A:** Generate `AGENTS.md` from the exact same template/render body as
  `CLAUDE.md` (zero duplication — one source), with one small, separately
  maintained Codex-appendix artifact appended by both producers at
  generation time. Nothing new to pin against drift; there is nothing left
  to duplicate.
- **B:** Maintain `AGENTS.md` as an independent template/render path per
  producer, pinned against `CLAUDE.md`'s content by a drift test (the same
  shape as today's `claude-md-template.md`-vs-renderer test).
- **C:** Do nothing — leave `AGENTS.md` generation unhandled; a Codex
  session in a Shipwright-managed project gets no Shipwright guidance at
  all today.

## Constraints that are not negotiable

none
