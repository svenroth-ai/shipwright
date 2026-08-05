# Mini-Plan: F5b dashboard regen tolerates WebUI's string-shaped test-status layers

- **Run ID:** iterate-2026-08-05-f5b-dashboard-webui-unit-shape

## Files to create/modify
- `shared/scripts/tools/update_build_dashboard.py` — edit. Replace the
  five inline `.get()` call sites in `_test_status_from_iterate` with two
  small tolerant helpers (`_layer_display`, `_smoke_display`) that branch
  on `isinstance(layer, dict)` vs `isinstance(layer, str)`.
- `shared/scripts/tests/test_build_dashboard.py` — edit. Add regression
  cases: string-shaped `unit`, mixed string+mapping in one block, blank
  string omitted.

## Work breakdown
1. Reproduce the crash with a WebUI-shaped fixture (string `unit`) calling
   `_test_status_from_iterate` directly. Confirm exact error site via
   traceback. Test expectation: manual repro script, not a committed test
   (already done — see spec's Confidence Calibration probe 1).
2. Write the failing pytest cases in `test_build_dashboard.py` first
   (webui string shape, mixed shapes, blank string) — confirm they fail
   against the unfixed code with the same `AttributeError`.
3. Implement `_layer_display`/`_smoke_display` and rewire
   `_test_status_from_iterate` to use them via a loop over the four
   `total`-bearing layers plus a separate smoke call. Test expectation: the
   3 new cases pass.
4. Run the full `test_build_dashboard.py` file plus the sibling
   `shared/tests/test_update_build_dashboard_skipped.py`,
   `test_render_determinism.py`, `test_build_dashboard_md_escaping.py` —
   confirm zero regressions.
5. Verify at the CLI level: invoke
   `update_build_dashboard.py --project-root <scratch> ...` against a
   WebUI-shaped `shipwright_test_results.json` in a throwaway scratch
   directory — confirm exit 0 and correct rendering (this is the literal
   "verify regeneration completes" AC, exercised via the real F5b call
   site, not just the unit-level function).
6. Lint the two changed files with the pinned ruff version.

## Data model changes
None — no schema change to `shipwright_test_results.json`; the fix is
read-side tolerance for a shape that was already being produced elsewhere,
not a new field.

## Test strategy
- Unit-level: `shared/scripts/tests/test_build_dashboard.py` — 3 new cases
  under `TestEventTestStatus`, existing 6 cases in that class serve as the
  no-regression pin for the mapping shape.
- No E2E needed: no UI/web surface. F0.5 surface is `cli` (see spec's
  `## Verification` section) — the pytest run against
  `TestEventTestStatus` IS the CLI surface runner, since those tests
  exercise the same `generate_dashboard()` path the real `update_build_dashboard.py`
  CLI entrypoint calls.

## Alternative approach (considered, rejected)
**Alternative: normalize at write time instead of read time** — teach this
monorepo's own F5 writer (or a migration/backfill script) to convert any
string-shaped `unit`/etc. into the dict shape before it ever reaches
`shipwright_test_results.json`, so the dashboard renderer never has to
branch on shape.

**Rejected because:**
1. The card is explicit: "Do not change the WebUI historical producer in
   this card." The string-shaped data originates in a *separate* repo
   (shipwright-webui) this monorepo does not control or ship — there is no
   write-time hook available here to normalize it before it lands in the
   WebUI-adopted project's `shipwright_test_results.json`.
2. Even a local migration/backfill pass would only fix *already-written*
   files, not the ongoing producer — the next WebUI iterate would
   regenerate a string-shaped `unit` and crash the dashboard again. The
   bug is a consumer-robustness gap, not a one-time data-cleanup problem,
   so a write-time fix does not close it.
3. Read-time tolerance is strictly smaller in scope (one function, no new
   migration script, no risk of mutating a file this monorepo does not own
   the writer for) and satisfies "normalize both documented shapes without
   weakening structured handling" directly — the structured path is
   untouched, the string path is now handled instead of crashing.
