# Completion Gate

Before marking the test phase complete, ALL test layers must have an explicit result:

| Layer | Required Result |
|-------|----------------|
| Unit tests | `pass` or `fail` (always required) |
| Integration tests | `pass`, `fail`, or `skipped: {reason}` |
| pgTAP tests | `pass`, `fail`, or `skipped: {reason}` |
| Smoke test | `pass`, `fail`, or `skipped: {reason}` |
| E2E tests | `pass`, `fail`, or `skipped: {reason}` |
| Consistency | `pass`, `warning`, or `skipped: {reason}` |
| Design fidelity | `pass`, `fail`, or `skipped: {reason}` |
| Performance | `pass`, `warning` (gate=warn), `fail` (gate=block), or `skipped: {reason}` |

If any layer has NO result (was never executed and has no skip reason):
- **Do NOT mark test phase as complete**
- Print warning: "Test layer {layer} has no result. Run it or document skip reason."
- Set phase status to `incomplete`

Valid skip reasons:
- `skipped: no testing.integration config in profile` (Integration)
- `skipped: tests/integration/ directory does not exist` (Integration)
- `skipped: missing integration test env vars` (Integration, local only)
- `skipped: no supabase/tests/database/ directory` (pgTAP)
- `skipped: no DEV URL available` (Smoke + E2E)
- `skipped: no Playwright config` (E2E)
- `skipped: profile has no UI` (E2E)
- `skipped: smoke test failed` (E2E, because prerequisite not met)
- `skipped: no .shipwright/designs/visual-guidelines.md` (Consistency)
- `skipped: profile has no UI` (Consistency)
- `skipped: no screen-routes.json` (Design fidelity)
- `skipped: profile opts out (testing.performance.enabled is false)` (Performance)
- `skipped: no dev_url available` (Performance — Lighthouse sub-check only)
- `skipped: no build artifacts found` (Performance — bundle sub-check only)
- `skipped: no bundle assets matched` (Performance — bundle sub-check, build_output_dir empty of *.js / *.css)
- `skipped: lighthouse_unavailable` (Performance — Node/Playwright/Chromium failure, see captured stderr)
