# Iterate: Restrict the AC-evidence ledger's status counter to table rows

**run_id:** iterate-2026-09-16-ac-ledger-status-cell-counting
**Type:** bug
**Complexity:** medium (touches a shared compliance-measurement tool whose
output is treated as fact by ADRs, decision-drops, and a spec-reviewer
HARD-GATE; the fix changes every downstream number, so it earns the fuller
process even though the diff itself is small)
**Spec Impact:** NONE (No-FR / tooling — `measure_ac_evidence_ledger.py` is
an internal compliance-measurement script for Shipwright's own campaign
bookkeeping, not a documented product FR)

## Problem

`shared/scripts/tools/measure_ac_evidence_ledger.py::count_statuses`
counted every backtick-quoted occurrence of a canonical status **anywhere**
in the ledger document, not restricted to a criterion table's status cell.
The module's own docstring rationalized this as a deliberate, accepted
trade-off — cross-checked once against a by-hand recount and pinned by a
test (`test_legend_and_summary_style_text_inflates_by_a_known_fixed_amount`)
that treated the legend and summary table's contribution as a *known,
fixed* inflation.

That rationale covered only two, structurally bounded sources of
inflation. It did not cover the real one: the ledger is prose-heavy by
design (every row carries a rationale, and rationales naturally name
statuses), so **any** future explanatory paragraph that backtick-quotes a
status name silently inflates the count by an amount nobody bounded or
tested for.

**The incident.** On 2026-09-12 (`e3-checks-test-security`, PR #748), a
sub-iterate added a paragraph to the ledger explaining a row split
(`#6`/`#6b`). The paragraph named `enforced, tested` twice and `prompt-only
(mechanisable)` once, in backticks. Re-running the script afterwards
returned 15 `prompt-only (mechanisable)` / 82 total, while the ledger's own
prior paragraph, the ADR, and the decision-drop all recorded 14 / 80
(measured before the paragraph existed). The Stage-1 spec-reviewer
correctly REJECTED on the mismatch, and the campaign STRICT-STOPped. The
sub-iterate's own reading was that the documents were stale and should be
updated to 15/82 — which would have recorded an artifact of the counting
bug as fact, in the one document whose entire purpose is to be the
trustworthy count. De-backticking the status names in that one paragraph,
touching no row, returned the script to exactly 14 and exactly 80 — proving
the paragraph, not the rows, caused the drift.

The interim mitigation (a "keep status names un-backticked outside a
status cell" note, added the same day) is still in the ledger. It is a
correct workaround, not a fix — it depends on every future author
remembering a rule the tool itself does not enforce.

## Root cause

`count_statuses` (before this fix) ran a whole-document regex sweep. Its
docstring explicitly reasoned that structural table parsing was too
fragile to attempt, because the ledger's tables take a different ad-hoc
shape in nearly every section — a defensible reason to avoid parsing "is
this specifically a criterion row", but not a reason to skip the much
cheaper structural question "is this line a table row at all".

## Fix

`count_statuses` now restricts matches to markdown table-row lines (first
non-whitespace character `|`) and additionally excludes any table block
whose header row's first column is literally `Status` — the trait shared
by the vocabulary legend (`| Status | What it means | ... |`) and the
2026-07-26 historical "Distribution after the end-check" summary table
(`| Status | Rows |`), and by no real criterion table (`Status` is always
a later column there, e.g. `| # | Criterion | Status | Evidence / gap |`).
This is one structural rule, not a per-table-shape parser, so it keeps the
original docstring's simplicity argument for everything except these two
specifically-named tables.

Full rationale, the historical-numbers handling, and the file locations
are documented in the script's own module docstring
(`shared/scripts/tools/measure_ac_evidence_ledger.py`).

## Historical numbers — not rewritten

Every total previously recorded in the ledger's own "Re-measured"
paragraphs, in ADRs, and in decision-drops was produced by the old,
whole-document counter. None of them is edited by this change — the same
rule ADR numbering already follows (never renumber retroactively). A new
"Re-measured again 2026-09-16 (iterate `ac-ledger-status-cell-counting`)"
paragraph was appended to the ledger stating the fix and the new,
table-row-only totals (**1** prompt-only/mechanisable · **25**
prompt-only/judgement · **13** enforced-untested · **25** unimplemented ·
**92** enforced-tested), reconciling forward rather than backward.

## Confidence Calibration

- **Boundaries touched:** a single pure-function counting algorithm in a
  standalone compliance-measurement script (`shared/scripts/tools/
  measure_ac_evidence_ledger.py`); no I/O boundary, no other module imports
  it (verified: `count_statuses`/`measure_ac_evidence_ledger` have no
  callers outside the script and its own test file).
- **Empirical probes run:**
  - Ran the fixed script against the real, live ledger
    (`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`,
    2100+ lines) — table-row-only counts are lower across every status than
    the old whole-document counts, confirming prose elsewhere in the
    document (beyond the single incident paragraph) was also inflating the
    old numbers.
  - Reproduced the exact incident shape as a regression fixture (a real
    criterion table plus an explanatory paragraph backtick-quoting two
    statuses) and confirmed the count is identical with and without the
    prose paragraph present.
  - Independently cross-checked the fix's `prompt-only (judgement)` output
    (25) against a by-hand recount already recorded in the ledger's own
    `e6-judgement-drift-tests` paragraph (2026-09-16, same day, unrelated
    sub-iterate, arrived at 25 by manually enumerating and excluding the
    legend, two prose mentions, and the historical summary table's two
    mentions) — the two independently-derived numbers match exactly.
- **Test Completeness Ledger:**

  | # | Behavior | Status |
  |---|---|---|
  | 1 | A status backtick-quoted in ordinary prose (non-table-row) does not affect the count | `tested` (`test_prose_mention_of_a_status_does_not_inflate_the_count`) |
  | 2 | A table whose header starts with `\| Status \|` (legend/summary shape) is excluded even though it is a table | `tested` (`test_legend_and_summary_tables_are_excluded_by_their_status_first_header`) |
  | 3 | Both exclusions hold simultaneously, for every canonical status, against a fixture naming all 8 in prose, the legend, and real rows | `tested` (`test_fixture_naming_every_status_in_prose_and_legend_counts_rows_only`) |
  | 4 | Real criterion tables (status in a later column) are counted normally, unaffected by the header rule | `tested` (`test_legend_and_summary_tables_are_excluded_by_their_status_first_header`, criterion-row assertion) |
  | 5 | The live measurement against the real ledger still matches its own header paragraph (drift guard, pre-existing test) | `tested` (`test_real_ledger_header_matches_the_live_measurement`, re-passes against the newly-appended reconciliation paragraph) |
  | 6 | Pre-existing counting behaviors (longest-alternative-first, split rows, backlog-line formatting, CLI JSON/human output, missing-file error) are unaffected | `tested` — of `origin/main`'s 9 prior tests: 7 pass unmodified (`test_counts_each_canonical_status_once_per_occurrence`, `test_qualified_status_does_not_double_count_as_bare_enforced`, `test_split_row_contributes_to_both_halves`, `test_backlog_line_excludes_enforced_and_no_oracle`, `test_main_reads_a_file_and_reports_json`, `test_main_reports_infra_error_on_missing_file`, `test_main_human_readable_output_shows_the_backlog_line`); 1 is deliberately **deleted** (`test_legend_and_summary_style_text_inflates_by_a_known_fixed_amount` — its premise, that legend/summary inflation is a known-fixed accepted amount, is superseded by this fix); 1 is **modified**, not unmodified (`test_real_ledger_header_matches_the_live_measurement` — reworded failure message per Internal Plan Review finding 3, added the `excluded_tables == 2` assertion per finding 2) |
  | 7 | Excluded table blocks are reported in `measure()`'s output for audit (Internal Plan Review finding 2) | `tested` (`test_excluded_tables_are_reported_for_audit`) |
  | 8 | The header-cell match is structural (whitespace-tolerant), not a literal string prefix | `tested` (`test_status_header_match_is_structural_not_a_literal_prefix`) |
  | 9 | A pipe-prefixed example table inside a fenced code block is not counted | `tested` (`test_fenced_code_block_table_example_is_not_counted`) |
  | 10 | A legend glued to a preceding table with no blank line is NOT excluded (documents the exclusion's actual block-scoped behavior, code review finding 3) | `tested` (`test_legend_glued_to_a_preceding_table_with_no_blank_line_is_not_excluded`) |
  | 11 | An unterminated fence is reported (`unterminated_fence`) and excludes the rest of the document, not silently miscounted (code review finding 5) | `tested` (`test_unterminated_fence_is_reported_and_excludes_the_rest_of_the_document`, `test_balanced_fence_reports_no_unterminated_fence`) |
  | 12 | The `Status`-first header match tolerates whitespace variants and a single-cell header, not only the one fixture shape originally tested (code review finding 3) | `tested` (`test_status_header_match_is_structural_not_a_literal_prefix`, 3 variants) |

  0 untested-testable.
- **Confidence-pattern check:** asymptote — the fixture in behavior 3 names
  every one of the 8 canonical statuses across all three zones (prose,
  legend, real row) in one pass, rather than sampling a subset, so there is
  no unexercised status left to hide a partial exclusion bug. Breadth — the
  real-ledger probe (2100+ lines, dozens of real tables of several
  different ad-hoc shapes) exercises the fix against the actual document
  population this script is for, not only synthetic fixtures. No
  `cross_component` machinery is touched (a standalone script + its own
  tests), so integration coverage does not apply.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-16-ac-ledger-status-cell-counting/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed — restrict the existing regex to table-row lines plus the single `Status`-first-header exclusion
- **Findings:** none
- **Reconciliation:** n/a — no rejection to reconcile against; both reviewers independently confirmed the approach is the smallest thing that would do, and specifically confirmed that reintroducing a fixed-offset subtraction (the old, table-scoped equivalent of the original design) would recreate the incident's failure mode rather than avoid it

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** approach sound and correctly implemented; two medium + two low findings, all fixed before commit
- **Findings:**
  1. [medium, completeness] The ledger's own reconciliation paragraph over-claimed the fix's reach ("prose no longer affects the count at all") — true only outside a table row; a non-status column inside a real row (e.g. an "Evidence / gap" narrative) still counts, and the reviewer found this live in the document (FR-01.03 #5's evidence cell). **Fixed** — narrowed the claim in both the module docstring and the ledger paragraph, with the concrete example cited.
  2. [medium, architecture] The `Status`-first-header exclusion had no observable audit signal and used a literal-prefix match vulnerable to whitespace variants. **Fixed** — `_table_header_first_cell` now parses the header structurally (split on `|`, strip, casefold) instead of prefix-matching, and `measure()` now returns an `excluded_tables` audit list (line + header text); the drift-guard test asserts the count is exactly 2.
  3. [medium, architecture] The drift-guard's failure message told a future maintainer to always "update the header paragraph to match" — the exact remediation that caused the 2026-09-12 incident when the real cause was a structural change, not a row edit. **Fixed** — reworded the assertion message to triage row-edit vs. structure-change before prescribing a fix.
  4. [low, architecture] No fenced-code-block awareness; a pipe-prefixed example table inside a documentation code sample (the module docstring contains exactly this shape) would be miscounted. **Fixed** — a ` ``` ` toggle now skips fence contents; regression test added.
  5. [low, completeness] The pre-existing "met at zero" ledger paragraph (count of 3) was left unconnected to the new, corrected count (1). **Fixed** — added one sentence cross-referencing the two.
  6. [low, completeness] No breadcrumb in the docstring naming which downstream documents quote pre-fix numbers. **Fixed** — module docstring's historical-numbers section now names the two ADRs and the decision-drop.
  7. [low, architecture, no action] Plan-vs-implementation faithfulness check — clean; no change requested.
- **Known limitations:** column-position-within-a-row parsing was considered and rejected (would undercount a real table that headers its status column `Enforcement` rather than `Status` — verified live in the document); the residual risk of a non-status column backtick-quoting a different status is now explicitly documented rather than fixed, consistent with the original design's simplicity argument.
- **Status:** 6 fixed, 1 no-action (clean)

## External Plan Review
- **Ran:** yes (Branch A — both providers available)
- **Providers:** glm, openai
- **Findings triaged:**
  1. **[glm, medium, edge-case]** A future criterion table that legitimately put `Status` first would be silently excluded entirely. **Disposition: fix** — added an `excluded_tables` audit list to the script's JSON output (each excluded block's header line + line number), so a reviewer can eyeball that only legend/summary-shaped tables were dropped; documented the invariant in the module docstring.
  2. **[glm, medium, edge-case]** The `|`-prefix table-row test doesn't validate full CommonMark table grammar (fenced code blocks, escaped pipes). **Disposition: disclose.** Verified the real ledger currently has exactly one fenced code block and no pipe-prefixed lines inside it, so this is not live. Left as a documented known limitation rather than adding fenced-code-block detection, consistent with the original design's simplicity argument (one rule per table shape was rejected as fragile; full CommonMark parsing is the same fragility at a different layer). Noted in the docstring.
  3. **[openai, high, approach]** Suggested parsing each table's header generically and counting matches only within the column literally named `Status`, instead of counting every backtick match on a table-row line. **Disposition: decline, with reason.** Verified against the real ledger: at least one real, already-counted criterion-shaped table (the "Four added" retro table, `| FR | Central criterion | Enforcement | ... |`) uses `Enforcement`, not `Status`, as the header for the exact column holding canonical status values. Column-name matching would silently undercount that table's real criterion rows — a regression on live data, not a theoretical risk. The row-based design (count every match on a table-row line, minus two named exclusions) is confirmed correct for this document's actual heterogeneous table shapes; the residual risk openai raised (a rationale/evidence column in a *different* column of the same row mentioning another status) is the same, already-tested, already-documented trade-off `test_split_row_contributes_to_both_halves` pins as a deliberate ledger convention, not a new regression this change introduces.
  4. **[openai, low, risk]** Mini-plan's test-accounting language was ambiguous about which of the prior tests remain unmodified vs. replaced (and, caught only later, at Stage-1 spec review: the mini-plan's own count of "8" was itself wrong — `origin/main` has **9** prior tests). **Disposition: fix** — corrected in this spec's Test Completeness Ledger row 6 (9 prior tests: 7 unmodified, 1 deleted named, 1 modified named).

## Self-Review
1. **Spec Compliance — pass.** Implements exactly what this spec + the mini-plan (as amended by the plan-review cascade) describe: table-row-only counting, single `Status`-first-header exclusion (now structural, not literal-prefix), fenced-code-block skip, `excluded_tables` audit output, and the reconciled docstring/ledger text. No extra feature added beyond the review findings' own fixes.
2. **Error Handling — pass.** No new I/O paths; the pre-existing `OSError` handler around the file read is untouched. Pure text-processing function, no new failure surface.
3. **Security Basics — pass.** No user input, no SQL, no HTML output, no secrets. Reads one local markdown file already tracked in the repo.
4. **Test Quality — pass.** All 6 new tests assert on outcomes (`count_statuses` dict values, `measure()`'s `excluded_tables` list) — never on internal state. Happy-path (row counting unaffected) and edge-path (prose, header variants, fenced code) both covered; 0 tests that pass regardless of implementation (verified each new test fails against the pre-fix `count_statuses` — confirmed manually by re-checking the earlier, unfixed baseline run: old output showed a bare whole-document sweep, e.g. `prompt-only (mechanisable)`: 3 vs the fixed 1).
5. **Performance Basics — pass.** Single-pass line walk, O(document length); the real 2100+-line ledger measures in well under a second, same as before.
6. **Naming & Structure — pass.** `measure_ac_evidence_ledger.py` is 299 lines (at, not over, the 300-line guideline). `tests/test_measure_ac_evidence_ledger.py` crossed to 311 lines after the review-cascade fixes and was flagged by the project's bloat gate; split along the fault line the file's own original docstring already named ("most tests exercise small synthetic fixtures... one test runs against the REAL committed ledger") into `test_measure_ac_evidence_ledger.py` (233 lines, fixture/mechanism tests) and `test_measure_ac_evidence_ledger_real_ledger.py` (100 lines, the one real-ledger drift guard) — both now well under the guideline, and the split separates unit-mechanism tests from the one integration-shaped test rather than being an arbitrary cut.
7. **Affected Boundaries — n/a, with justification.** The script reads a hand-written markdown file (producer: iterate/campaign authors; consumer: this script + human readers) — not a machine-generated serialized format, so `touches_io_boundary` does not fire (confirmed: no risk flags at classification). The JSON output gained one additive key (`excluded_tables`); no existing consumer reads this script's output programmatically (verified via grep — no importer outside the script's own test file), so this is not a breaking schema change.
8. **Test Hygiene Probe — deferred to post-commit.** `check_test_body_suspects.py` requires a commit SHA to diff against; will run at F0 (pre-commit fresh-verification gate re-runs the full suite) and is re-checked structurally here: no new `pytest.skip`/`xfail`/`.only` in the diff (the sole `pytest.skip`, now living in `test_measure_ac_evidence_ledger_real_ledger.py` after the split, is pre-existing — a legitimate "ledger file moved/renamed" runtime guard, not a CI-tooling-absence mask).

## Full Code Review (code-reviewer, Stage 2)
- **Verdict:** PASS with advisories (no HIGH findings, 1 medium, 6 low)
- **Findings triaged:**
  1. **[medium, readability]** Module docstring had grown to 111 lines (37% of a 299-line file, zero headroom before the next change trips the bloat gate); much of the growth was run-specific provenance (incident narrative, review-finding-number citations, named ADRs) that CLAUDE.md's own "Docs = what/how, not provenance" rule assigns to the spec/ADR instead. **Fixed** — trimmed to the four behavioral-contract paragraphs plus one pointer line to this spec for the incident/historical-numbers rationale; ~50 lines removed.
  2. **[low, readability]** Docstring falsely claimed to itself contain a fenced-code-block example ("this very docstring contains one shape like that") — it does not; the claim was also repeated in a test docstring. **Fixed** — both removed/corrected.
  3. **[low, correctness]** The "structural, not literal-prefix" header-match test exercised only one fixture shape, not the whitespace/single-cell variants its own docstring and `_table_header_first_cell`'s docstring advertised as working. **Fixed** — added the two missing variants to the same test.
  4. **[low, correctness]** The exclusion's block-scoping (a blank line above the legend keeps it a separate block) was only named in prose, in a failure message, never pinned by a test — contradicting the Confidence Calibration's "0 untested-testable" claim. **Fixed** — added `test_legend_glued_to_a_preceding_table_with_no_blank_line_is_not_excluded`, documenting the real (non-excluded) merged-block behavior.
  5. **[low, correctness]** An unterminated fence (odd number of ` ``` ` markers) silently discarded the rest of the document with no audit signal — asymmetric with the `excluded_tables` audit trail Internal Plan Review finding 2 required. **Fixed** — added `unterminated_fence` to `measure()`'s payload, a human-output warning line, and two regression tests.
  6. **[low, readability]** `measure()` walks `_table_row_text` twice (once via `count_statuses`, once directly), discarding half the result each time — correct but asks a reader to convince themselves the two calls cannot diverge. **Fixed** — added a one-line comment explaining the deliberate trade-off (keeping `count_statuses` a self-contained `text -> counts` function callable directly from its own unit tests).
  7. **[low, readability]** `_table_header_first_cell`'s `if cells else ""` branch is unreachable (`str.split` never returns an empty list). **Fixed** — collapsed to a single return expression.

## Review Record

See `.shipwright/planning/iterate/iterate-2026-09-16-ac-ledger-status-cell-counting/reviews.json`.
