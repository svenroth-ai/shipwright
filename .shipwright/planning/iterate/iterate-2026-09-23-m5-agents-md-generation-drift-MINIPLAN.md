# Mini-Plan: R4 extended — AGENTS.md generation in adopt + project

## Context

R4's original scope (already implemented, uncommitted in this same worktree/
branch) fixed drift between THIS repo's own hand-maintained root `CLAUDE.md`
and `AGENTS.md`, and stripped hardcoded Codex model/reasoning-effort prose
from `AGENTS.md`. That fix does not help any OTHER Shipwright-managed
project: `/shipwright-adopt` and `/shipwright-project` only ever scaffold a
target project's `CLAUDE.md` — no `AGENTS.md` is ever written there.

**Revised justification (post architecture-review round 1 — openai reject,
glm revise; round 2, corrected, both approve):** the load-bearing reason is
NOT the Claude Code 2.1.277 CLAUDE.md-absent fallback (Shipwright already
writes `CLAUDE.md` unconditionally, so that fallback firing is rare and
self-inflicted). The real reason: **Codex CLI reads `AGENTS.md` as its own,
native, first-class convention — not a fallback.** Today a Codex session in
ANY Shipwright-managed project gets zero Shipwright guidance, regardless of
whether `CLAUDE.md` exists.

This mini-plan covers closing that gap for BOTH producers.

## Decisions (confirmed with the operator)

1. **Shared-source generation, not two hand-maintained templates.** The
   existing `claude-md-template.md` vs. `claude_md_renderer.py` pair is
   split-brain by design (that module's own docstring says so) and a test
   (`test_claude_md_template.py`) exists ONLY because drift between them was
   already a real, shipped bug. AGENTS.md must not repeat that pattern: the
   shared body (WHAT/HOW/Structure/Review-subagents/Editing-this-file/
   Asking-questions) is rendered from ONE source and reused for both files;
   only a short, clearly separate Codex appendix differs.
2. **Greenfield always writes both files**, unconditionally, whenever
   `/shipwright-project` scaffolds `CLAUDE.md` — no interview-gated opt-in.
3. **Load-bearing threshold for an existing AGENTS.md in adopt: 1024 bytes**,
   same constant/semantics `is_loadbearing_claude_md` already uses for
   CLAUDE.md.
4. Codex appendix content: the activation-record/PreToolUse-gate mechanism
   description (real, code-enforced, Codex-only — no CLAUDE.md equivalent)
   plus generic conduct bullets (isolated worktree/branch, preserve
   unrelated changes, OpenRouter-authorized reviews, no derived snapshots,
   `deliver_pr.py` DELIVERED gate). Explicitly **no** model slug or
   reasoning-effort value anywhere (this run's earlier, already-implemented
   decision for this repo's own AGENTS.md applies here too — those are
   resolved dynamically by `codex_review_model_resolution.py`, never
   restated in generated prose).
5. **(Architecture review, round 2, both approve) Single render source for
   BOTH producers, not a second template file.** `AGENTS.md` = the exact
   same shared body `CLAUDE.md` already gets (`claude-md-template.md` for
   greenfield, `claude_md_renderer.py`'s body for brownfield — unchanged),
   plus ONE small, separately-maintained Codex-appendix **file**
   (`shared/templates/codex-agents-md-appendix.md`) that both producers read
   at generation time — adopt's Python reads it directly (no hardcoded
   duplicate string), project's agent-driven instructions load the same
   file. Nothing to pin with a drift test: there is only one copy of
   everything (the shared body is literally the same read; the appendix is
   literally the same file both paths load).

## Design

### 1. `shared/templates/codex-agents-md-appendix.md` (new)

The ONLY new content artifact. Short (~20-40 lines): the activation-record/
PreToolUse-gate description + generic Codex conduct bullets (decision 4),
no model/effort values. Both producers read this exact file — nothing about
it is duplicated anywhere.

### 2. `plugins/shipwright-adopt/scripts/lib/claude_md_renderer.py` (small addition, no refactor of the CLAUDE.md path)

- `_render_claude_md` gains one new parameter, `host_name: str = "Claude Code"`,
  substituted into the one sentence in the shared body that names the host
  tool ("`{host_name}` withholds subagent spawning until the user asks").
  Default preserves CLAUDE.md's exact existing output — `write_claude_md`
  calls it unchanged. (Plan-review round 1, glm medium: reusing the body
  verbatim would ship "Claude Code withholds..." into a Codex-read file —
  this repo's own root AGENTS.md/CLAUDE.md pair already treats that same
  sentence as legitimately per-runtime, not shared prose.)
- Add `write_agents_md(project_root, ...)`: calls `_render_claude_md(...,
  host_name="Codex")` for the shared body, reads
  `codex-agents-md-appendix.md` from `shared/templates/` via a
  walk-up-from-`__file__` helper (mirrors `codex_activation_mint.py`'s
  `_find_shared_scripts()` pattern — proven to resolve from both the
  monorepo checkout and the installed plugin cache, since
  `update-marketplace.sh` syncs `shared/` into
  `cache/shipwright/shared/`; plan-review round 1, both reviewers medium),
  appends it, and writes with the same load-bearing-preservation flow
  `write_claude_md` uses. Generalize
  `is_loadbearing_claude_md`/`preserve_if_exists`/`record_preservation_action`
  (`preserve_existing.py`) to take a `rel_path`/filename parameter instead
  of being CLAUDE.md-hardcoded (same 1KB threshold, decision 3; plan-review
  round 1, openai medium: thread the filename explicitly through the whole
  chain rather than leaving any CLAUDE.md-specific name/key hardcoded), and
  generalize `_append_standing_request`'s idempotent-append behavior
  similarly — but for a preserved/oversized existing AGENTS.md, append
  **both** the review-cascade standing-request section **and** the Codex
  appendix (plan-review round 1, openai medium: appending only the
  standing-request section would mean a project with its own large AGENTS.md
  never receives the activation-gate guidance at all, defeating this
  feature for exactly the users most likely to already run Codex).
- `generate_adoption_artifacts.py`: call `write_agents_md` alongside
  `write_claude_md`.

### 3. `project-scaffolding.md`

New "AGENTS.md" step alongside the existing "1. CLAUDE.md" step: reuse the
SAME filled `claude-md-template.md` content from step 1 (not a second
template load), append `codex-agents-md-appendix.md`'s content verbatim,
write unconditionally (decision 2).

### 4. `docs/hooks-and-pipeline.md`

Update the artifact-write matrix: adopt and project now also write
`AGENTS.md`. Per GLM's round-2 low-severity suggestion, the test added in
item 6 below also asserts the appendix file exists, so a future rename is
caught at the same place a matrix-staleness reminder would fire.

### 5. This repo's own root `templates/` Structure line

List the appendix file by its **real name**, not an "AGENTS.md" alias
pointing at a differently-named file (plan-review round 1, low, both
reviewers: aliasing recreates the exact "label says one thing, file is
another" ambiguity this run's first half fixed). `templates/` line becomes
`# CLAUDE.md, codex-agents-md-appendix.md, .shipwright/agent_docs, CI
templates`; `shared/tests/test_agents_md_claude_md_parity.py`'s
`TEMPLATE_LABEL_TO_PATH` drops the `"AGENTS.md"` key and adds
`"codex-agents-md-appendix.md": "codex-agents-md-appendix.md"`.

### 6. Tests

- New unit coverage for `write_agents_md` mirroring
  `test_artifact_writer_data_preservation.py` /
  `test_claude_md_standing_request_append.py` (load-bearing preserved,
  backup written, idempotent append, shared body matches
  `_render_claude_md`'s own output byte-for-byte, appendix content present).
- A lightweight existence/reference check that `project-scaffolding.md`
  names `codex-agents-md-appendix.md` by its real path (mirrors
  `test_template_warns_against_other_skills`'s substring-check style) so a
  rename doesn't silently orphan the instruction.
- `shared/tests/test_agents_md_claude_md_parity.py`: re-add the "AGENTS.md"
  label to both root files' `templates/` line and fix the now-stale comment.
- **`test_claude_md_template.py` and `test_artifact_writer_data_preservation.py`
  / `test_claude_md_standing_request_append.py` stay green, unedited** —
  the regression proof that CLAUDE.md's own generation is untouched.

## Out of scope

- Codex model/role resolution mechanism itself (already correct, prior
  campaign work).
- `.codex/agents/*.toml` generator (cut round 1, this run).
- Any change to how Claude Code vs. Codex actually choose between
  CLAUDE.md/AGENTS.md at runtime (host behavior, not Shipwright's).

## Risk

- Touches 2 plugins (`shipwright-adopt`, `shipwright-project`) +
  `shared/templates` + `shared/tests` + `docs/hooks-and-pipeline.md` —
  cross-plugin surface, complexity treated as medium.
- No refactor of `_render_claude_md`/`write_claude_md` — `write_agents_md`
  is additive, calling the existing function unchanged. Its own existing
  test suite staying green, unedited, is the regression guard.

## Architecture review

Round 1 (brief justified via the Claude Code 2.1.277 fallback): openai
reject, glm revise — both converged on the same two points (weak stated
justification; the `agents-md-template.md` + byte-identity-test design
reproduces the drift shape this run's first half fixed). Round 2 (brief
corrected to the real justification — Codex reads AGENTS.md natively —
design simplified to one appendix file, no second template, no new drift
test): openai approve, glm approve (two low-severity, out-of-scope
suggestions noted, not actioned this run — see reviews.json).

## Plan review

Round 1: openai revise, glm revise. Both flagged the same high-severity
issue (the sub-iterate spec's acceptance criteria still described the
round-1, since-abandoned `agents-md-template.md` design — fixed, spec ACs
now match round-2). Substantive medium findings integrated into the design
above: `host_name` parameterization (Claude-specific prose was about to ship
into AGENTS.md verbatim), the walk-up path-resolution helper for the new
runtime file read, appending both sections (not just the standing-request
one) to a preserved oversized AGENTS.md, and explicit filename-parameterized
tests for the generalized preservation/append helpers. Two low-severity
items also integrated: the Structure-line label fix (§5) and an explicit,
documented accepted-risk note that greenfield AGENTS.md correctness is
verified the same (instruction-only) way CLAUDE.md's greenfield output
already is today — not a new gap this design introduces.
