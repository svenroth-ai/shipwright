# Mini-Plan: Restrict the AC-evidence ledger's status counter to table rows

**run_id:** iterate-2026-09-16-ac-ledger-status-cell-counting

## 1. Files to create/modify

- `shared/scripts/tools/measure_ac_evidence_ledger.py` — edit:
  restrict `count_statuses` to markdown table-row lines; exclude any table
  block whose header's first column is `Status`; rewrite the module
  docstring's "deliberate simplicity trade-off" section to describe the new
  behavior and the historical-numbers policy.
- `shared/scripts/tools/tests/test_measure_ac_evidence_ledger.py` — edit:
  replace `test_legend_and_summary_style_text_inflates_by_a_known_fixed_amount`
  (its premise — that legend/summary inflation is accepted — is superseded)
  with regression tests covering prose-does-not-inflate (the incident's own
  shape), `Status`-first-header exclusion (structural, not literal-prefix),
  a combined fixture naming every canonical status in prose + legend +
  rows simultaneously, the `excluded_tables` audit output, and fenced-code
  skipping (review-cascade findings). Split into this file (fixture tests)
  plus new `test_measure_ac_evidence_ledger_real_ledger.py` (the one
  real-ledger drift-guard test) once the fixture file crossed 300 lines.
- `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  — edit: append one new "Re-measured again 2026-09-16" paragraph (new
  entry, existing entries untouched) stating the fix and the new,
  table-row-only totals, so the pre-existing drift-guard test
  (`test_real_ledger_header_matches_the_live_measurement`) keeps passing
  against the corrected method.
- `.shipwright/planning/iterate/2026-09-16-ac-ledger-status-cell-counting.md`
  (this run's iterate spec, new file).

No other file references `count_statuses` or imports
`measure_ac_evidence_ledger` (verified via grep) — no downstream consumer
to update.

## 2. Work breakdown

1. Restructure `count_statuses` to build a table-row-only view of the
   document (contiguous `|`-prefixed line blocks), excluding blocks whose
   header starts with `| Status |`, then run the existing longest-
   alternative-first regex sweep over that view instead of the raw text.
   Test: the 9 pre-existing unit tests must still pass unmodified (pins the
   sweep mechanics), plus the 3 new tests below. [Corrected post-hoc,
   Stage-1 spec review: originally miscounted as 8 — see the iterate
   spec's Test Completeness Ledger row 6 for the actual per-test outcome,
   since one of the 9 (the legend/summary "known fixed inflation" test)
   was deliberately deleted rather than kept passing, and one other was
   modified, not left unmodified.]
2. Add regression tests: prose-does-not-inflate (reproduces the incident
   shape exactly), `Status`-first-header exclusion (legend + summary shape,
   with and without a real criterion table alongside), and the combined
   all-8-statuses fixture the fix's own spec calls for.
3. Rewrite the module docstring's rationale section — the "known accepted
   imprecision" framing no longer describes the code.
4. Run the fixed script against the real, live ledger; compare to the old
   script's output to confirm the new counts are lower (expected — prose
   elsewhere in the 2100+-line document was also inflating the old numbers,
   not only the one incident paragraph).
5. Append the new "Re-measured" paragraph to the ledger with the new
   totals, explicitly stating prior totals are not rewritten.
6. Re-run the full `shared/scripts/tools/tests` root — the pre-existing
   `test_real_ledger_header_matches_the_live_measurement` drift guard (now
   in the sibling `test_measure_ac_evidence_ledger_real_ledger.py` after
   the §1 split) must pass against the newly-appended paragraph.

## 3. Component hierarchy

N/A — not UI.

## 4. Data model changes

None.

## 5. Test strategy

Unit tests only, against the real script and both synthetic fixtures and
the real, live ledger file (already tracked in the repo — no new fixture
file needed). No E2E; this is a CLI reporting tool with no `dev_url`
surface, `touches_io_boundary` does not apply (reads a file, writes
nothing), `touches_build`/`cross_component` do not apply.

## 6. Alternative approach

**Considered:** parse each table's actual column position and read only
the literal "status cell" per row (true structural table parsing), as a
more precise alternative to "count every backtick match on a table-row
line, minus two named exclusions."

**Rejected because:** this is exactly what the original script's docstring
already argued against, and that argument still holds — the ledger's
tables take a different ad-hoc shape in nearly every section (plain
criterion table, 2-column "what stood first instead" table, retro-scenario
recap table, bare bullet lists that aren't tables at all), so reading "the
status cell" would need one column-position rule per shape and would
silently miss the next shape a future walk invents. The row-vs-prose
restriction plus a single `Status`-first-header exclusion fixes the actual
incident (prose inflation) and the two known bounded sources (legend,
summary) without reintroducing that fragility, at the cost of still
counting a backticked status if it appears in a non-status column of a
real table row — an existing, already-tested, and much rarer edge case
(`test_split_row_contributes_to_both_halves` documents the ledger's own
convention of using such combined cells deliberately, not as a defect).
