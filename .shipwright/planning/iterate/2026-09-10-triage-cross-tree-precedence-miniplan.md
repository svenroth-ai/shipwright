# Mini-Plan: triage-cross-tree-precedence

- **Run ID:** iterate-2026-09-10-triage-cross-tree-precedence

## Files to create/modify
- `shared/scripts/triage.py` — edit: split `_iter_raw_lines` into a local-only
  reader and a local+foreign union, and change `read_all_items`'s pass 2 to
  apply the new precedence rule; update the docstrings that describe the old
  "no origin privilege" rule.
- `shared/scripts/lib/triage_cross_tree.py` — edit: module docstring note
  clarifying that `read_all_items` (unlike the advisory `pendingDelivery`
  marker) now gives local decisions absolute precedence over a foreign
  `status` event for the same id.
- `shared/tests/test_triage_cross_tree_delivery.py` — edit: replace
  `test_a_foreign_tie_is_broken_by_file_order_not_origin` with a pointer
  comment (tests moved out, see below).
- `shared/tests/test_triage_cross_tree_precedence.py` (new, split at 300
  lines) — the core precedence regression tests: an exact-timestamp tie
  where local wins outright (rewrite of the old, now-wrong test), the exact
  measured defect (chronologically-LATER foreign status still loses to
  local), `amend` staying chronological, a local decision living in the
  OUTBOX ONLY still blocking a foreign override (D1 union — external/internal
  review finding), and a MALFORMED local status event (bad `newStatus`) not
  blocking a legitimate foreign gap-fill (internal review finding — the
  local-decided-ids gate filters by `newStatus in STATUSES`, the same
  validity check pass 2 already applies and `lib.triage_delivery.
  foreign_undelivered_from_records` already mirrors).
- `shared/tests/test_triage_cross_tree_precedence_edgecases.py` (new, split
  at 300 lines) — multiple foreign status events for a never-locally-decided
  id still resolve chronologically among themselves (external review
  finding — the drop-filter must remove ONLY a foreign status whose id is
  locally decided, not collapse the foreign side generally); a local+foreign
  `amend` at an EXACT timestamp tie still resolves by file order, unaffected
  by the new precedence rule (external review finding); the
  `category:"integration"` compose test (local tracked/outbox reader +
  cross-tree sibling reader, same read, two different ids).
- `.shipwright/planning/iterate/2026-09-10-triage-cross-tree-precedence.md` —
  already created (Step 1); Confidence Calibration filled after Build.

## Work breakdown
1. Write the two new failing regression tests in
   `test_triage_cross_tree_delivery.py` (chronologically-later foreign status
   loses to a local decision; amend stays chronological) — confirm RED against
   the current code.
2. Rewrite the now-contradicted tie-break test to assert the corrected
   behavior — confirm it also fails RED against current code (proves it was
   actually exercising the old, wrong precedence).
3. Implement the precedence rule in `triage.py`: split local vs. foreign raw
   lines (single read, reused for both the id-set and the merged list — no
   double I/O), compute the set of ids with a VALID (`newStatus in STATUSES`)
   local `status` event, drop any foreign `status` event whose id is in that
   set before pass 2's sort/apply. Keep `amend` resolution unchanged
   (chronological, local or foreign, regardless of local status).
4. Run the full `test_triage_cross_tree_delivery.py` file plus
   `test_triage_cross_tree_error_paths.py`, `test_triage_cross_tree_discovery_edge_cases.py`,
   `test_triage_gc.py`, `test_triage_reader_integrity.py`, and the full
   `shared/tests` suite for regressions.
5. Update docstrings (`triage.read_all_items`, `triage._iter_raw_lines`,
   `lib/triage_cross_tree.py` module docstring) to describe the corrected
   precedence rule in the same diff (Test-Update-Klausel).
6. File a triage card for the two out-of-scope follow-ups named in the spec
   (WebUI TS parity; full fan-out/parse-cost fix) so they are not silently
   dropped.

## Test strategy
- Pure unit/regression tests against `triage.read_all_items` using the
  existing `_make_main`/`_make_worktree` tmp_path fixture helpers already in
  `test_triage_cross_tree_delivery.py` — no live E2E surface (no UI, no
  server) is implicated, so no Playwright/browser layer is needed.
  `cross_component`'s Integration Coverage requirement is met by a test that
  exercises the union of (a) this tree's own tracked+outbox files and (b) a
  simulated sibling tree's tracked log together through the public
  `read_all_items` entry point — the same shape the module's own existing
  tests already use, tagged `category:"integration"` in the Test Completeness
  Ledger.

## Alternative approach (rejected)
**Alternative: filter foreign records at the source** — have
`lib.triage_cross_tree.foreign_status_and_amend_records` take the caller's
already-known local status ids and drop matching foreign `status` records
before they are even returned, rather than filtering inside
`triage.read_all_items`'s pass 2.

**Rejected because:** it would require `triage_cross_tree.py` to import from
`triage.py` to learn the local status ids (or have `triage.py` pass a
freshly-computed set down into a lower-level module on every call), inverting
today's clean one-directional dependency (`triage.py` → `lib.triage_cross_tree`)
and duplicating the same "local status ids" computation both call sites would
otherwise need. It would also entangle `foreign_status_and_amend_records`
(used elsewhere: `cross_tree_delivery_facts` for the advisory `pendingDelivery`
marker, which must NOT gain this precedence rule — a sibling's stale reopen is
still correctly flagged as an undelivered pending decision even when this
tree's own tracked log later overrode it) with a precedence policy that only
`read_all_items` should apply. Keeping the filter inside `read_all_items`
keeps the module boundary `lib/triage_cross_tree.py` already documents intact:
that module only ever *reports*, and only the board's own resolution logic
*decides*.
