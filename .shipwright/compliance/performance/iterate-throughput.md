# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-09-12-e3-checks-test-security`

**Pre-instrumentation run** — no `iterate_timings` recorded (predates this measurement). Not zero duration; simply not measured.

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 2.4 min | 10.0 min | 3 |
| implementation | 24.2 min | 38.2 min | 5 |
| verification | 19.4 s | 4.9 min | 8 |
| review | — | — | 0 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-09-11-ci-supplychain-ack-authorship` | 76.0 min | 4.4% | 0/4 | 0 | degraded |
| `iterate-2026-09-11-t2-triage-inbox` | — | — | — | — | pre-instrumentation |
| `iterate-2026-09-12-retention-cap-headroom` | 45.9 min | 23.5% | 1/4 | 0 | degraded |
| `iterate-2026-09-12-keystone-helper-sensitive-path` | 47.4 min | 81.0% | 0/5 | 0 | degraded |
| `iterate-2026-09-12-agent-doc-budget-anchor-falsematch` | 69.2 min | 83.6% | 1/5 | 0 | degraded |
| `iterate-2026-09-12-t3-plan-design` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-09-12-review-evidence-canonical-names` | 115.8 min | 38.1% | 1/5 | 0 | degraded |
| `iterate-2026-09-12-t4-test-security` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-09-12-test-results-orphan-triage` | 36.7 min | 73.6% | 0/5 | 0 | degraded |
| `iterate-2026-09-12-e3-checks-test-security` | — | — | — | — | pre-instrumentation |
