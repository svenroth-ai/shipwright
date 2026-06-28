# Iterate Spec: cc3 — AR-05 RTM "Reconciled?" column + readability (consumes BP-2)

> Campaign `2026-06-27-compliance-control-coverage`, sub-iterate **cc3** (final).
> Scope authority: `campaigns/2026-06-27-compliance-control-coverage/sub-iterates/cc3-ar05-rtm-reconciled.md`.
> Intent: CHANGE · Complexity: medium · Risk: none · Spec Impact: NONE (compliance tooling, no product FR).

## Goal

Surface BP-2's per-FR reconciliation in the Requirements Traceability Matrix and
make the matrix readable, **reusing the exact same `_reconciliation` helper the
Control-Grade dimension consumes** so the grade and the RTM can never disagree.
Six concrete changes in `plugins/shipwright-compliance/scripts/lib/rtm_generator.py`:

1. **`Reconciled?` column** on the Requirements Coverage table, keyed on
   `compute_reconciliation(work_events).status(fr_id)`:
   ✅ = behavior-affected FR re-verified since its last change ·
   ⚠️ needs re-verification = behavior changed, not yet re-tested ·
   — = not behavior-touched.
2. **Replace** the age-based `> 14 days` stale clause (`_frs_with_stale_verification`)
   in the Coverage Summary with a reconciliation-driven **"FRs needing
   re-verification"** subsection (touched-without-re-verify, **never age**).
3. **Full FR titles** (drop the 60-char truncation on the coverage table).
4. **Clickable `evt-` evidence** — iterate event ids in "Verified By" link to the
   matching row anchor in the Verification Timeline.
5. **Test-column legend** decoding `Tests` (`passed/total`; `X → Y` progression),
   `Last tested`, and `Reconciled?`.
6. **Rename** `Last Verified` → neutral **`Last tested`** (age is not a penalty).

## Affected Boundaries

- **Compliance artifact** `.shipwright/compliance/traceability-matrix.md` (rendered
  markdown only — no wire-format / config / state change).
- **Shared SSOT consumed (not changed):** `_reconciliation.compute_reconciliation`
  (the BP-2 helper also read by `_control_block.build_grade_inputs`).
- **Docs:** guide.md RTM section (column + `Last tested`).

## Approach

- Lazy-import `compute_reconciliation` inside the render functions (mirrors this
  file's existing lazy `triage` import — keeps RTM generation crash-free in
  minimal envs and avoids pulling the `audit_adapters` sys.path surgery into the
  module-import surface).
- `Reconciled?` and the "needs re-verification" subsection both read the helper,
  so the per-row column and the summary list agree by construction; both are
  filtered to declared requirements (the RTM iterates requirements), exactly as
  `build_grade_inputs` filters its sets — that is the grade ↔ RTM agreement.
- Age is never consulted: an old-but-re-verified behavior touch reads ✅ forever;
  the removed `_STALE_VERIFICATION_DAYS` / `_reference_now` machinery is deleted.
- `evt-` links: validate the canonical `evt-<hex>` shape before interpolating
  (defense-in-depth, mirroring the existing `_TRIAGE_ID_RE` guard); add a matching
  `<a id="evt-…">` anchor to the Verification Timeline event cell.

## Confidence Calibration
- **Boundaries touched:** rendered `traceability-matrix.md` only (coverage table +
  coverage-summary subsections + verification-timeline anchors). No wire-format,
  config, state, or scorer change.
- **Empirical probes run:** (1) real-repo regeneration — the live event log yields
  the same behavior-touched / unreconciled FR set the Control-Grade dimension
  reports (4 behavior-touched, 0 unreconciled → all ✅, no "needs re-verification"
  subsection), confirming grade ↔ RTM agreement on real data; (2) age-alone
  fixture — a 2020 behavior touch that WAS tested renders ✅ and is absent from the
  subsection (proves age never flags); (3) `evt-` link round-trip — a rendered
  `evt-…` ref resolves to a `<a id="evt-…">` anchor present in the same document.
- **Test Completeness Ledger:** recorded in `shipwright_test_results.json`
  `iterate_latest.test_completeness` at F5.
- **Confidence-pattern check:** depth — per-status rendering, age-neutrality,
  link-shape validation, full-title escaping each probed; breadth — column,
  summary subsection, legend, link, rename, and removed-clause each covered;
  integration — RTM column and grade dimension proven to read the one helper and
  agree on both real data and a synthetic fixture (`category:"integration"`-style
  agreement test).
