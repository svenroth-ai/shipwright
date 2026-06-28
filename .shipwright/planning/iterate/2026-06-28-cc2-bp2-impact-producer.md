# Iterate Spec: cc2 — BP-2 per-FR impact producer → light reconciliation

> Campaign `2026-06-27-compliance-control-coverage`, sub-iterate **cc2**.
> Scope authority: `campaigns/2026-06-27-compliance-control-coverage/sub-iterates/cc2-bp2-impact-producer.md`.
> Intent: CHANGE · Complexity: medium · Risk: `touches_io_boundary` · Spec Impact: NONE (compliance tooling, no product FR).

## Goal

Persist a structured **per-FR behavior-impact map** (`fr_impact`) on `work_completed`
events, read it back tolerantly, and use it to **light the Control-Grade
"Change reconciliation" dimension** (n/a → live) — without touching the
repo-agnostic scorer. The same reconciliation helper is the SSOT cc3 (AR-05)
reuses for the RTM "Reconciled?" column, so the grade dimension and the RTM
column can never drift.

## Affected Boundaries

- **Event wire-format** (`shipwright_events.jsonl`): new optional `fr_impact`
  object on `work_completed`. Producers: `record_event.py` (CLI + `build_event`)
  and `finalize_iterate.py` (worktree F5b path, via `event_extras`).
- **Reader**: `WorkEvent` / `WorkEvent.from_dict` (compliance collectors).
- **Grade adapter**: `_control_block.build_grade_inputs`.

## Approach

- `fr_impact` = `{FR-id: impact}` where impact ∈ `add|modify|remove|none`
  (the same vocab as event-level `spec_impact`). add/modify/remove are
  behavior-affecting; none = referenced-but-preserving.
- Validation SSOT: `shared/scripts/lib/fr_classification.normalize_fr_impact`
  (raises on malformed structure; reused by both producers). Reader coerces
  tolerantly (legacy/null/garbage → `{}`), never crashes.
- Reconciliation (`_reconciliation.compute_reconciliation`): per-FR latest
  behavior-affecting touch vs latest tested event referencing the FR;
  reconciled iff `latest_verify_ts >= latest_touch_ts`. **Age is never a
  signal.** Falls back to event-level `spec_impact`+`affected_frs`/`new_frs`
  for pre-BP-2 events so the dimension measures real history.
- `build_grade_inputs` filters the helper's sets to declared requirement ids
  (so grade ↔ RTM agree) and flips `reconciliation_measurable`.

## Confidence Calibration
- **Boundaries touched:** event wire-format (`fr_impact` on `work_completed`);
  `WorkEvent`/`from_dict` reader; `build_grade_inputs` grade adapter.
- **Empirical probes run:** (1) event-log census — 215 work_completed, 9
  behavior-affecting (`spec_impact=modify`), 4 with FR linkage, all 4 tested →
  fallback yields 4 behavior-touched FRs, 0 unreconciled (rec_score 1.0, grade
  stays A); (2) round-trip write→read of `fr_impact` through record_event +
  finalize; (3) doc-only / spec_impact=none touch contributes 0 behavior-touched.
- **Test Completeness Ledger:** recorded in `shipwright_test_results.json`
  `iterate_latest.test_completeness` at F5.
- **Confidence-pattern check:** depth — boundary round-trip + tolerant-read +
  malformed-reject probes; breadth — producer (2 paths), reader, helper, grade
  adapter each covered; integration — reconciliation helper is the single SSOT
  for grade + RTM (cc3), proven by the helper test + adapter test agreeing.
