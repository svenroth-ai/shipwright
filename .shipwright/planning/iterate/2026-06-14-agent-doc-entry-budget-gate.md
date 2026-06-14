# Iterate: agent-doc entry budget — durable repo-agnostic gate + cleanup

- **Run ID:** iterate-2026-06-14-agent-doc-entry-budget-gate
- **Intent:** CHANGE (framework mechanism + curated-doc cleanup)
- **Complexity:** medium (history-calibrated)
- **Spec Impact:** MODIFY (entry-writing rules + enforcement) + cleanup

## Problem

The "≤600 chars, one-line pointer" rule for the always-loaded agent docs
(`## Architecture Updates`, `## Convention Updates`, `## Learnings`) keeps
failing: entries grow back into multi-hundred-word bold paragraphs. Root causes:

1. **Enforcement is monorepo-only.** The rule is enforced solely by
   `plugins/shipwright-iterate/tests/test_agent_doc_entry_rules.py` (a monorepo
   pytest). Adopted repos (e.g. shipwright-webui) get the *instructions*
   (F2.md / reflection.md) but **no gate** → the 2026-06-14 webui Architecture
   entries (~900 + ~1500 chars) sailed in right after the 2026-06-12 condense
   iterate. (Codebase's own learning: *prose-only "always" steps get skipped —
   convert to a gate*.)
2. **Date-regex hole exempts the bold Learnings format.** The gate parses dates
   as `(YYYY-MM-DD)` only. The dominant Learnings format `- **rule** (iterate-…-slug)`
   has its date only inside the run-id slug → `entry_date()` returns None →
   treated as undated → exempt → grows unbounded.
3. **Two competing Learnings formats** (date-lead non-bold per reflection.md vs.
   bold-lead from the compaction iterate) → "alle fett und nicht schön formatiert".
4. **Blank-line writer bug.** `write_decision_log._append_architecture_update`
   appends `"\n- … \n"` to a file already ending in `\n` → a blank line before
   every release-folded ADR bullet.
5. **run_id↔ADR duplication.** Release aggregation appends an `ADR-NNN` bullet
   without removing the pre-release verbose `run_id` bullet → two bullets per
   shipped iterate.

## Acceptance Criteria

- **AC1 — repo-agnostic gate.** A shared, repo-agnostic checker flags an
  over-budget NEW/changed entry under any of the three sections, runnable in ANY
  project (monorepo + adopted). Wired into the iterate finalization so it
  enforces in webui too (ships via plugin cache).
- **AC2 — date-regex hole closed.** `entry_date()` extracts the date from a
  run-id slug (`(iterate-YYYY-MM-DD-…)` / `… YYYY-MM-DD …`) as well as a bare
  `(YYYY-MM-DD)`, so the bold Learnings format is no longer exempt.
- **AC3 — single SSoT for entry-parsing.** `iter_entries` / `entry_date` /
  budget logic live once in a shared lib; the monorepo pytest imports them.
- **AC4 — blank-line writer fixed.** `_append_architecture_update` produces a
  single `\n`-separated bullet (no blank line between ADR bullets); covered by a
  test.
- **AC5 — instructions unified + clear.** F2.md + reflection.md + the section
  header comments state ONE canonical format per section and point to the
  repo-agnostic command. Learnings format is date-lead, no bold.
- **AC6 — cleanup (monorepo).** `architecture.md` (Architecture Updates) +
  `conventions.md` (Learnings + Convention Updates) compacted to uniform
  one-liners ≤600 chars, no blank lines, run_id↔ADR de-duplicated, no info loss
  (detail already in decision_log.md / `_archive-agent-doc-updates.md`).
- **AC7 — cleanup (webui).** Same cleanup applied to the webui repo's two files
  as a SEPARATE commit/PR in `C:\01_Development\shipwright-webui` (different repo).

## Canonical formats (the SSoT the docs must state)

- **Architecture Updates / Convention Updates** (`component`/`data-flow` →
  architecture.md; `convention` → conventions.md):
  `- **<run_id|ADR-NNN>** (YYYY-MM-DD): <impact> — <one sentence>. → decision_log.md (Run-ID/ADR)`
  bold ANCHOR only, no blank lines, ≤600 chars.
- **Learnings**:
  `- (YYYY-MM-DD) <phase> — <one-line rule>. → <run_id|ADR-NNN>`
  no bold, date-lead, ≤600 chars.

## Affected Boundaries

- Producer/consumer: the markdown bullet is written (write_decision_log /
  hand-append) and consumed by the budget checker → round-trip test.
- Test-Update-Klausel: changing the gate's parsing rules updates F2.md +
  reflection.md in the same diff.

## Out of scope / follow-ups

- Auto-dedup in the release aggregator (remove the run_id bullet when its ADR
  bullet is appended) — cleanup handles existing dupes by hand; aggregator
  dedup is a separate follow-up.
- Shipping the monorepo pytest itself into adopted repos (the runtime gate
  covers adopted repos instead).

## Confidence Calibration
- **Boundaries touched:** the agent-doc markdown bullet — written by
  `write_decision_log` / hand-append, consumed by the budget checker
  (`lib.agent_doc_budget`). A producer↔consumer round-trip boundary.
- **Empirical probes run:**
  - `check_agent_doc_budget.py --all` on the cleaned monorepo docs → `OK`
    (0 over-budget; was 10 before cleanup).
  - Forward-only git-base mode proven by `test_check_agent_doc_budget.py`
    (new oversize flagged, untouched legacy oversize ignored, no-git no-op).
  - `entry_date` run-id-slug parsing proven by hermetic tests (the closed hole).
  - blank-line writer fix proven by `test_arch_update_writer_format.py`.
  - pinned phrases ("Backend-affects-Frontend", "spec-only authorship counts
    as no test") confirmed present post-cleanup; hook-fanout-dedup run_id
    (impact=convention drop) retained in Convention Updates.
- **Test Completeness Ledger:**
  | Behavior | Disposition | Evidence |
  |---|---|---|
  | iter_entries splits multi-line bullets | tested | test_agent_doc_budget |
  | entry_date parses bare + slug + comma date; ignores prose date | tested | test_agent_doc_budget |
  | over_budget honors enforced_from + exempts undated | tested | test_agent_doc_budget |
  | new_over_budget = forward-only diff | tested | test_agent_doc_budget + test_check_agent_doc_budget (git) |
  | CLI full-corpus + forward-only + no-git no-op | tested | test_check_agent_doc_budget |
  | F11 verifier wiring + drift-guard | tested | test_verify_iterate_finalization |
  | writer no-blank-line | tested | test_arch_update_writer_format |
  | monorepo gate consumes shared SSoT + hole closed | tested | test_agent_doc_entry_rules |
  | docs cleaned ≤600, no info loss, pinned phrases kept | tested | full-corpus scan OK + pinned-phrase tests |
  0 testable-but-untested.
- **Confidence-pattern check:** depth — gate logic unit-tested incl. the
  closed-hole regression; breadth — all 3 sections + both modes + writer +
  verifier covered; composition — the F11 verifier→CLI→lib chain proven with a
  real git repo (`test_check_agent_doc_budget` forward-only). Not a
  `cross_component` machinery change (no merge/churn/hook-fanout/pipeline-validator
  touched), so no `category:"integration"` ledger row required.
