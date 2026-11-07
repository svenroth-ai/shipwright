# Architecture Brief

**Need:** an operator-started e2e harness (integration-tests/e2e-webui) must be able to judge a built skill-companion app against a second package (21 capabilities with testable Fit criteria) with its own checklist; the existing fixtures keep working.

**Options**
1. A fixture-keyed checklist plus a separate check suite (new folder of small modules) that starts the built backend itself against local fake servers; shared modules get only additive hooks.
2. Extend the existing Variant interface (api/board/selfContained) with the new checks and reuse the preview-started app on the fixed port.
3. A standalone script outside the Playwright spec that runs the same checks against any running app.
4. Python/pytest conformance suite in the repo, run against a built project directory.

**Constraints:** no real network or keys; checks must be unit-testable with synthetic input; files stay under the 300-line cap; the package is untouched.
