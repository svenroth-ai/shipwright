# Step 3.5: E2E Results Verification

After E2E tests complete, verify consistency across all result sources. This catches
miscounts from setup projects, retries, or skipped tests.

1. Read `e2e-results.json` (Playwright's authoritative output):
   - Parse `stats.expected`, `stats.unexpected`, `stats.skipped`, `stats.flaky`
   - Filter: only count tests from the `chromium` project (exclude `setup` project tests)
2. Compare against `shipwright_test_results.json` e2e counts:
   - `e2e.total` should match Playwright's `expected + unexpected + skipped` (chromium only)
   - `e2e.passed` should match `expected`
3. **If numbers diverge:**
   - Analyze WHY: setup project counted? Retries inflating counts? Skipped tests miscounted?
   - Fix `shipwright_test_results.json` to match Playwright's authoritative numbers
   - Add `"e2e_verification_note"` field documenting the discrepancy and resolution
4. **If numbers match:** proceed silently
5. Verify `playwright-report/index.html` exists — note path for compliance linking
