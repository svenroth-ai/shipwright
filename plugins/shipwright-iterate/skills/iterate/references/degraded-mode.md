# Degraded Mode

When metadata is incomplete:

- **No sync config:** default to medium complexity, run full test suite.
- **Stale mappings:** note in summary, conservative defaults.
- **No visual-guidelines.md:** skip design check, note in ADR.
- **Browser verify fails to start:** fall back to test-only verification.
- **Code-reviewer unavailable:** self-review only, flag in ADR as
  "review-limited".
- **review.py unavailable / no API key + user chose skip:** Branch B
  Option 2 — fall back to the mandatory self-review that already ran,
  log the opt-out (with reason) in the iterate ADR, write
  `external_review_state.json` marker with
  `status: skipped_user_opt_out`.
- **Pipeline handoff fails:** print manual instructions + handoff file
  path.
- **No `.shipwright/designs/screens/`:** skip mockup comparison in
  design fidelity check, design_fidelity marked "degraded", note in
  ADR.

Record all degraded conditions in `shipwright_test_results.json` →
`degraded` array.
