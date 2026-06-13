# Iterate: guide.md correctness audit + fix

- **run_id:** iterate-2026-06-13-guide-correctness-audit
- **type:** change (documentation correctness)
- **complexity:** medium
- **spec_impact:** none (documentation only; no FR/spec behavior changes)

## Intent

Systematically verify `docs/guide.md` against the actual codebase (SKILL.md files,
`shared/profiles/*.json`, hooks, `shared/constitution.md`, `shared/glossary.md`,
audit scripts), recent commits, and ADRs — then correct every confirmed
discrepancy. Triggered by user doubt that the prior install-only iterate (#228)
had actually verified the whole guide. It had not.

## Method

7 parallel verification sub-agents (model=opus), one chapter-block each, each
returning a `file:line`-backed discrepancy ledger. Chapters 2/12 were already
verified in #228. Consolidated result: **21 guide.md discrepancies** + **6
findings where the code/SKILL.md is stale and the guide is correct** (the latter
deferred to a separate follow-up iterate — NOT fixed here, no silent code-to-doc
edits).

## Acceptance criteria (the 21 fixes)

WRONG: §1 "7 check groups"→8; §10 "7 check groups"→8 (A–H); §4.2 drop "sprint"
agent_doc; App.A "sprint status"→"build dashboard"; §4.5 branch
`{project-slug}/NN-name`→`build/{slug}-{session-id}`; §8 risk taxonomy
"Eight"→"Eleven" + add touches_build/touches_io_boundary/cross_component rows;
§8 run-table "8"→"11" flags; §9 tier split "20/16"→"24/12"; §11 opt-out file
`shipwright_plan_config.json`→`shipwright_iterate_config.json`; App.B
"Groups C+F shipped; A/B/D/E/G planned"→"A–H all shipped".

OUTDATED/IMPRECISE: §4.1 "installs suggest_iterate.py"→plugin-registered; §4.5
"two-tier review"→spec→code→doubt cascade; §4.10 F5 marker→arch.md-text
reconcile; §9 handoff Stop-hook→gitignored runtime mirror; §9
destructive-migration drop "without matching down.sql"; §6 "OSS is the default"→
auto-detect probes Aikido first; §1 "4 severity categories"→"4 error
categories"; App.B "all under tools/"→mark-review-state.py under checks/.

MISSING: §4.11.1 add `gh-prompt:{owner}/{repo}` action-unit; §4.7 mention CI
prompt-injection scanner; §8 Override Classes Mandatory += iterate_history +
Confidence Calibration (medium+).

## Deferred to a separate follow-up iterate (code/SKILL.md stale, guide right)

C1 compliance SKILL.md only documents 7 groups (omits H); C2/C3 run+build
SKILL.md banners + setup_implementation_session.py docstring stale branch form +
"sprint"; C4 group_f.py:386 stale registration label; C5 vite-hono.json Node
22.x vs notes "20.x"; C6 glossary.md:56 "six SDLC phases" miscount.

## Confidence Calibration
- **Boundaries touched:** `docs/guide.md` only (no I/O boundary; pure doc text).
- **Empirical probes run:** 7 opus sub-agents cross-checked all 13 chapters
  against source with file:line evidence → 21 guide discrepancies confirmed, 6
  code-side findings separated out; chapters 2/3/3.5/12/13 + most of 4 verified
  accurate.
- **Test Completeness Ledger:** recorded in `shipwright_test_results.json` at F5.
- **Confidence-pattern check:** breadth = every chapter audited by a dedicated
  agent; depth = each fix carries source `file:line` evidence; residual risk =
  no automated guide↔code linter exists (manual re-read + path-canon lints).
