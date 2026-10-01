# Iterate: Codextender reviewers are Agent-tool subagents

Run: `iterate-2026-10-01-codextender-agent-tool-review-dispatch` · Type: CHANGE · Complexity: small · Spec Impact: NONE

## Problem
Codextender (Claude Code redirected to a non-Anthropic backend through a proxy that maps subagents to `sol`)
spawns spec/code/doubt-reviewer through the Agent tool (observed: sessions 81aef475, f785bdbd; `review_via_codex.py` never ran).
Two doc defects follow:
1. The internal architecture review is skipped under Codextender (`iteration-planning.md` Step 3.5 step 0b and plan
   `step-5-int-arch.md` skip on `--driver codex` OR `CODEXTENDER_ACTIVE`, recording
   `Ran: no (no Codex transport for architecture_internal yet)`), although the Agent tool works there.
2. `shared/prompts/codex_review_dispatch.md` told a Claude Code session "redirected to a non-Anthropic backend" to dispatch
   via `review_via_codex.py`. Sessions do not, and it buys no independence: the `codex exec` default review model
   (`CODEX_REVIEW_MODEL`) is `gpt-6.1-sol`, the same family as Codextender's `sol`.

## Acceptance Criteria
- AC1: The architecture-internal skip applies only when the harness itself is Codex CLI; under Codextender the
  skill spawns `shipwright-plan:architecture-internal-reviewer` and records `Ran: yes` (iterate + plan).
- AC2: `codex_review_dispatch.md` and every dispatch pointer state the real rule: Codex CLI driving →
  `review_via_codex.py`; Claude Code incl. Codextender → Agent-tool subagents (proxy-mapped).
- AC3: The external-review `--driver` mapping (`CODEXTENDER_ACTIVE` → `codex` → `{glm, opus}`) is kept — it answers
  a different question (the diff's author was Codex-backed), and is documented as such.
- AC4: A drift test fails if the skip clause keys on `CODEXTENDER_ACTIVE` again or the dispatch doc loses the rule.

## Out of scope
Codex Light parity (card 19). A real Codextender iterate verifying `Ran: yes` — only possible in a Codextender
session, flagged in the run summary.
