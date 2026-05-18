# Mini-Plan: phase-quality-check-fixes

- **Run ID:** iterate-2026-05-18-phase-quality-check-fixes
- **Type:** change · **Complexity:** medium

## Approach

Three independent, additive check-side fixes. Each follows the same shape:
keep the existing primary path; add a fallback that recognises a convention
the check predates; the fallback never false-PASSes because it reads
authoritative evidence written at the same finalization point as the
primary signal. Mirror the `check_c4_decision_log_has_phase_adr`
`if phase == "iterate"` precedent.

## Files to change

| File | Change |
|---|---|
| `shared/scripts/tools/verifiers/common.py` | C5: extract inline check into `_check_inline_unreleased_category`, add `_count_changelog_drop_files` + category-agnostic fallback. C1: add `_C1_TERMINAL_PHASE_HISTORY_OUTCOMES` frozenset, add docstring + iterate (`work_completed`/decision-drop) + any-phase (`phase_history`) fallbacks; restructure so the `phase_history` fallback runs even with an empty event log. |
| `shared/scripts/lib/spec_parser.py` | S1: `read_top_level_spec` falls back to `sorted(.shipwright/planning/*/spec.md)` first match when `agent_docs/spec.md` is absent; extend docstring + module docstring. |
| `shared/tests/test_verifiers_common.py` | +C5 drop-dir tests (drop PASS, category-agnostic, inline-wins, neither-fails, `.gitkeep`-ignored); +C1 tests (iterate work_completed, iterate decision-drop, phase_history any-phase, phase_history with empty event log, non-terminal outcome fails, no-evidence fails). |
| `shared/tests/test_spec_checks.py` | +`read_top_level_spec` tests (canonical, planning fallback, deterministic multi-split, canonical-wins, neither→None) + S1 end-to-end on adopted layout. |
| `docs/hooks-and-pipeline.md` | § "Minimum Phase Completion Canon": document C1 evidence sources (work_completed / decision-drop / phase_history) and the C5 drop-directory model. |

## Work breakdown (TDD order)

1. **RED** — write all new tests in both test files; run → they fail.
2. **GREEN-C5** — `_count_changelog_drop_files` (checks `project_root` and
   `project_root.parent`, recursive `**/*.md`, `.gitkeep` excluded) +
   restructured `check_c5_...` (inline-first, drop-dir fallback).
3. **GREEN-S1** — `read_top_level_spec` planning-glob fallback.
4. **GREEN-C1** — `_C1_TERMINAL_PHASE_HISTORY_OUTCOMES` +
   restructured `check_c1_...` (event → iterate fallback → phase_history
   fallback → fail; fallbacks reachable with empty `events`).
5. Run new tests → green. Run full `shared/tests/` → green.
6. Docstrings + `docs/hooks-and-pipeline.md`.
7. Confidence Calibration probes (producer-shape round-trips), Self-Review,
   Code Review, F0 full suite, F0.5 cli surface.

## Test strategy

- **C5:** drop file under a *different* category than the one C5 was called
  with → must PASS (category-agnostic). Inline bullet present → PASS without
  needing drops. `.gitkeep`-only drop dir → FAIL. Neither → FAIL.
- **S1:** adopted layout (no `agent_docs/spec.md`, real
  `planning/01-adopted/spec.md`) → reader returns content AND
  `check_s1_top_level_spec` returns PASS. Both files present →
  `agent_docs` wins. Multi-split → `01-` sorts first. Neither → `None`.
- **C1:** iterate `work_completed[source=iterate]` → PASS; pending
  decision-drop → PASS; `phase_history[test]=[{outcome:"adopted-skipped"}]`
  with **no event log** → PASS; non-terminal outcome → FAIL; nothing → FAIL.
  All three existing C1 tests must stay green.
- **Regression:** full `shared/tests/` suite at F0 (shared infra — every
  plugin's Stop-hook auditor consumes these checks).

## Alternatives considered

- **C1 — gate the `phase_history` fallback on an `adoption` key in
  run_config (adopted-projects-only).** Rejected: the user specified "for
  ANY phase", and a terminal `phase_history` entry is authoritative
  completion evidence regardless of adoption — it is written at the same
  finalization point as the `phase_completed` event, so it cannot
  false-PASS. Gating on adoption adds a conditional with no safety benefit
  and leaves orchestrated projects' `phase_history` unused.
- **C5 — category-specific drop count (the original proposal text).**
  Rejected per the operator decision: a bug-only iterate writes only a
  `Fixed/` drop, so a category-specific check (called with `Added` for the
  iterate phase) would keep false-failing. Category-agnostic answers the
  real question — "did the phase record a changelog entry at all".
- **S1 — move `_AGENT_DOCS_DIRNAME`/`_PLANNING_DIRNAME` above
  `read_top_level_spec` to remove the forward reference.** Rejected as
  scope creep: the existing `read_top_level_spec` already forward-references
  `_AGENT_DOCS_DIRNAME` (call-time resolution); adding a `_PLANNING_DIRNAME`
  reference is strictly consistent with the file's current idiom.
