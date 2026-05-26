# Results Enforcement

Test results determine pipeline continuation:

| Layer | On FAIL | Rationale |
|-------|---------|-----------|
| **Unit tests** | **Pipeline stops** (blocking) | Unit tests are deterministic — failure = real bug |
| **Integration tests** | Autofix (3 retries, fast-fail for infra), then blocking | Deterministic against real DB |
| **pgTAP tests** | Autofix (3 retries), then blocking | Schema-level verification |
| **Smoke test** | **Pipeline stops** (blocking) | App not running = can't deploy |
| **E2E tests** | **Warning only** (non-blocking) | E2E can be flaky; log failures but continue |
| **Consistency** | **Warning only** (non-blocking) | Cross-page cosmetic issues don't gate deployment |
| **Design fidelity** | **Warning only** (non-blocking) | Fidelity divergence != broken functionality |
| **Performance** | **Warn (default)** / **Block (opt-in via profile or test_config)** | Discipline gate: `warn` ships honest signal without breaking flow; `block` once project has calibrated budgets |

If unit tests, integration tests, pgTAP tests, or smoke test FAIL: set phase status to `FAIL` and inform user. Do NOT proceed to deploy.
