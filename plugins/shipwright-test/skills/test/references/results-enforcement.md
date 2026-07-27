# Results Enforcement

Test results determine pipeline continuation:

| Layer | On FAIL | Leaves behind | Rationale |
|-------|---------|---------------|-----------|
| **Unit tests** | **Pipeline stops** (blocking) | — (the run stops) | Unit tests are deterministic — failure = real bug |
| **Integration tests** | Autofix (3 retries, fast-fail for infra), then blocking | — (the run stops) | Deterministic against real DB |
| **pgTAP tests** | Autofix (3 retries), then blocking | — (the run stops) | Schema-level verification |
| **Smoke test** | **Pipeline stops** (blocking) | — (the run stops) | App not running = can't deploy |
| **E2E tests** | **Warning only** (non-blocking) | triage item per failing spec file (`test-warning:e2e:{file}`) | E2E can be flaky; log failures but continue |
| **Consistency** | **Warning only** (non-blocking) | triage item per inconsistent category (`test-warning:consistency:{category}`) | Cross-page cosmetic issues don't gate deployment |
| **Design fidelity** | **Warning only** (non-blocking) | triage item per diverging screen (`test-warning:fidelity:{screen}`) | Fidelity divergence != broken functionality |
| **Performance** | **Warn (default)** / **Block (opt-in via profile or test_config)** | triage item per failed metric (`perf:{metric}:{page}`) | Discipline gate: `warn` ships honest signal without breaking flow; `block` once project has calibrated budgets |

**A failure that does not stop the run still leaves a tracked follow-up.** A
warning printed to a terminal is gone when the session ends, and a suite that
has been failing for six weeks then looks exactly like one that broke this
morning. The performance budget always worked this way; the other three
non-blocking layers were brought in line by
`warning_followups.py` (Step 5.0). Follow-ups deduplicate on the *finding*, not
the commit, so a persistent failure stays exactly one open item.

**Two things never become follow-ups:**

- **Known-and-accepted failures** — anything declared in
  `shipwright_known_failures.json`, the same list the audit phase reads. They
  are reported separately in the summary and file nothing; they are not new
  work. An *unreadable* list excuses nothing.
- **A test that only passed on retry** is not a failure at all. It stays a pass
  and does not block, and gets its own low-severity item so a test that has
  needed a retry for weeks becomes visible before it fails for good.

If unit tests, integration tests, pgTAP tests, or smoke test FAIL: set phase status to `FAIL` and inform user. Do NOT proceed to deploy.
