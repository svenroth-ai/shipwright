# Iterate Spec — P3.1 Reviewer Stack (SP1 spec-reviewer + OS3 doubt-reviewer)

- **Run ID:** `iterate-2026-05-30-reviewer-stack`
- **Triage ID:** `trg-7c6137ed` (P3.1 Reviewer Stack — SP1 + OS3)
- **Intent:** FEATURE (new framework capability — two reviewer subagents + orchestration)
- **Complexity:** medium — `cross_split` (changes span shipwright-build +
  shipwright-iterate plugin surfaces) forces a medium floor: full review + full
  test suite. Classifier under-estimated (`trivial`, 0.6 conf, below 0.7);
  overridden to medium per spec §6 (P3.1 = "M — 1 Iterate") and the cross-plugin
  scope chosen at interview.
- **Spec Reference:** `Spec/external-frameworks-integration.md` §2 (SP1 + OS3
  spec-items), §6 (P3.1 bundle), §1.1 (boundary with Campaign A.review — A.review
  only added the Bloat-Checklist header to the EXISTING `code-reviewer.md` /
  `sub-iterate-runner.md`; this iterate creates NEW reviewer agents).

## Problem

Build Step 6 today is a single quality gate: self-review → internal `code-reviewer`
subagent (5-axis) → optional external cascade. Two adversarial patterns from the
external-frameworks research are not yet wired:

- **SP1 (Superpowers two-stage review):** there is no dedicated *spec-compliance*
  gate that runs BEFORE the quality review. A diff that diverges from the section
  spec is only caught incidentally inside the 5-axis `correctness` axis, mixed with
  quality findings. The README already advertises the `spec-reviewer → code-reviewer`
  two-stage pattern (README L374) — but `agents/spec-reviewer.md` does not exist.
- **OS3 (Osmani doubt-driven):** non-trivial decisions (migrations, async/concurrency,
  cross-plugin imports, irreversible ops) get no fresh-context, disprove-biased
  adversarial pass before commit. `agents/doubt-reviewer.md` does not exist.

This iterate adds both reviewer agents and orchestrates the three-stage cascade
**spec-reviewer (HARD-GATE) → code-reviewer (quality) → conditional doubt-reviewer
(advisory-must-address)** in the guided build path, and wires the autonomous
sub-iterate-runner delegation path (interview Q3).

## Spec Impact (FEATURE → classify)

**NONE** against any app `spec.md`. Framework-internal change to plugin runtime
prompts (`agents/*.md`, `SKILL.md`, `references/*.md`) + drift-protection meta-tests.
The shipwright monorepo is an adopted `library`-scope project with no FR rows
tracking plugin-prompt wording. Recorded in the iterate ADR.

## Interview Decisions (locked)

- **Q1 — Reviewer scope vs external review:** INTERNAL-ONLY. `spec-reviewer` and
  `doubt-reviewer` are always internal Claude subagents with bespoke role prompts.
  The optional Step 6c external cascade stays a generic code-quality second opinion
  on the diff; it is NOT extended into spec-compliance or doubt passes (avoids
  duplicating role logic into external prompt templates and limits diff exposure).
- **Q2 — doubt-reviewer gating:** ADVISORY-MUST-ADDRESS. `doubt-reviewer` surfaces
  disprove-biased objections AFTER `code-reviewer` passes; the implementer MUST
  respond in writing to each (fix or reasoned rebuttal), but a reasoned rebuttal may
  proceed to commit. Only `spec-reviewer` is a HARD-GATE that blocks `code-reviewer`.
- **Q3 — orchestration scope:** ALSO wire the autonomous path. The
  `sub-iterate-runner.md` Step 3.7 delegation is reworded (net-zero, anti-ratchet)
  to name the full cascade, with substantive detail in the non-frozen
  `references/iteration-reviews.md`.

## Acceptance Criteria

1. **AC-1 (spec-reviewer agent):** `plugins/shipwright-build/agents/spec-reviewer.md`
   exists, ≤400 LOC (~150 target), carries a **HARD-GATE** tag (Superpowers style),
   an adversarial spec-compliance prompt that cites the specific spec line/section a
   divergence violates, emits structured JSON with a PASS/REJECT verdict, and an MIT
   attribution footer to obra/superpowers (© Jesse Vincent).
2. **AC-2 (doubt-reviewer agent):** `plugins/shipwright-build/agents/doubt-reviewer.md`
   exists, ≤400 LOC (~150 target), is a fresh-context prompt **biased to disprove**
   (assume the change is wrong until shown otherwise), documents the file-touch trigger
   heuristic (migrations, async/concurrency, cross-plugin imports, irreversible ops),
   marks itself ADVISORY-MUST-ADDRESS (not a hard blocker), and an MIT attribution
   footer to addyosmani/agent-skills (© Addy Osmani).
3. **AC-3 (guided orchestration):** build Step 6 orchestrates
   `spec-reviewer → code-reviewer → conditional doubt-reviewer`. The substantive flow
   (order, HARD-GATE re-review loop on spec REJECT, doubt-reviewer trigger heuristic,
   advisory-must-address semantics, internal-only decision) lives in
   `references/code-review.md`; the Kern `SKILL.md` Step 6 gets a minimal pointer and
   stays ≤300 LOC.
4. **AC-4 (spec-divergent probe):** on a deliberately spec-divergent diff,
   `spec-reviewer` REJECTs with an explicit spec-line citation and `code-reviewer` is
   NOT invoked until the re-review passes. (Documented as the contracted flow + pinned
   structurally; behavioral execution is a prompt-execution probe.)
5. **AC-5 (doubt trigger probe):** a diff touching `supabase/migrations/*.sql` invokes
   `doubt-reviewer` AFTER `code-reviewer` passes; a diff touching only `README.md` does
   NOT (trivial-change heuristic). Both branches are documented in `code-review.md` and
   pinned by the orchestration test.
6. **AC-6 (autonomous path):** `sub-iterate-runner.md` Step 3.7 names the full
   reviewer cascade delegation (spec-reviewer + code-reviewer + conditional
   doubt-reviewer) back to the orchestrator (runner has no `Agent` tool), net-zero LOC;
   `references/iteration-reviews.md` carries the substantive iterate-side cascade detail.
   The existing `test_sub_iterate_runner_contract.py` stays green (all Step 3.5–3.8
   labels/cross-refs preserved).
7. **AC-7 (tests):** `plugins/shipwright-build/tests/test_reviewer_orchestration.py`
   (NEW, ≤300 LOC) pins: both agents exist; HARD-GATE tag on spec-reviewer; disprove
   bias + heuristic on doubt-reviewer; MIT footers on all three reviewers; cascade
   order documented in `code-review.md`; doubt heuristic includes the migrations trigger
   and excludes docs-only; all three reviewer prompts ≤400 LOC.
8. **AC-8 (no bloat trip):** each `agents/*.md` ≤400 LOC; build Kern ≤300; test ≤300;
   `code-review.md` + `iteration-reviews.md` ≤400; the two frozen runner files
   (`section-builder.md` 486, `sub-iterate-runner.md` 479) are NOT grown (net-zero) —
   no new bloat-baseline crossing.

## Affected Boundaries

- `plugins/shipwright-build/agents/spec-reviewer.md` (NEW)
- `plugins/shipwright-build/agents/doubt-reviewer.md` (NEW)
- `plugins/shipwright-build/tests/test_reviewer_orchestration.py` (NEW)
- `plugins/shipwright-build/skills/build/SKILL.md` (Step 6 minimal pointer — ≤300 LOC)
- `plugins/shipwright-build/skills/build/references/code-review.md` (orchestration detail)
- `plugins/shipwright-iterate/agents/sub-iterate-runner.md` (Step 3.7 reword — net-zero)
- `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md` (cascade detail)

No `*_config.json` / `*_state.json` / `.env*` / `hooks.json` touched →
`touches_io_boundary` NOT set. No app web/CLI surface touched. `section-builder.md`
(build autonomous, inline review, no Agent tool) is intentionally left unchanged: it
is bloat-frozen at 486 LOC and its inline review already covers spec-compliance
(Step 10.1) + quality; the dedicated subagent cascade is a guided + iterate-runner
concern. The `/shipwright-run`-orchestrated build-autonomous cascade is noted as a
follow-up (the run orchestrator, not this PR, would spawn the new subagents).

## Confidence Calibration

- **Boundaries touched:** two NEW agent prompts + one NEW meta-test + four edited
  runtime-prompt docs across two plugins. All markdown/prose + pytest drift-protection.
  No serialized-format producer/consumer, no runtime config IO.
- **Empirical probes run:**
  - `test_reviewer_orchestration.py` RED before (26 failed / 6 passed), GREEN
    after (32 passed). Confirms the structural contract is actually enforced.
  - Net-zero on the frozen runner: `sub-iterate-runner.md` = 479 LOC post-reword
    (== baseline `current` 479); `anti_ratchet_check.py --worktree` →
    `{"ratchets": [], "new_crossings": []}`. Also confirmed the Stop-gate
    (`bloat_gate_on_stop.py`) normalizes the marker path and filters the 479
    "crossing" because it is in-baseline — so no false Stop-block.
  - `test_sub_iterate_runner_contract.py` → 37 passed AFTER the reword (all Step
    3.5–3.8 labels + `reviews` subkeys preserved).
  - LOC budgets measured post-edit: spec-reviewer 107, doubt-reviewer 109, Kern
    294 (≤300), code-review.md 222, iteration-reviews.md 312, test 287 — all under.
  - Full suites GREEN: build 84, iterate 258, integration 136 (+2 deselected).
  - External LLM review (OpenRouter, Branch A) run on the staged diff → one
    substantive spec-mismatch finding (spec-reviewer trigger ≠ 6b trigger) +
    three test-hardening notes; all four addressed (see ADR dispositions).
- **Edge cases NOT probed + why acceptable:** the runtime *behavioral* acceptance
  (a live probe-build where spec-reviewer rejects spec-divergent code; doubt-reviewer
  fires on a migration but not on README) are prompt-execution probes that cannot be
  asserted from pytest. They are covered structurally — the order, HARD-GATE,
  heuristic, and gating semantics must exist and be wired in the prompts the agent
  reads; the live behavior follows from those prompts.
- **Confidence-pattern check (asymptote):** primary failure mode is a silent
  anti-ratchet trip (a frozen file grew) or a Kern over 300 LOC — both caught by the
  full suite + anti-ratchet check, so the green gate is the empirical floor.

## Out of Scope

- Extending the external cascade (6c) into spec/doubt passes (Q1 = internal-only).
- Growing `section-builder.md` / the `/shipwright-run` build-autonomous orchestrator
  to spawn the new subagents (noted as follow-up).
- README/guide.md Acknowledgments edits — the two-stage pattern is already credited
  in README L374; doubt-reviewer attribution lives in its own file footer.
- P3.2 Code-Simplify skill (OS1) — separate bundle.
