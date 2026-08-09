# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the 5 groups that can — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-08-09-test-evidence-freshness-w3`

**Pre-instrumentation run** — no `iterate_timings` recorded (predates this measurement). Not zero duration; simply not measured.

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | 11.0 min | — | 1 |
| planning | 2.6 min | 4.1 min | 4 |
| implementation | 37.8 min | 69.4 min | 2 |
| verification | 16.7 s | 159.4 min | 8 |
| review | 0.0 s | 51.4 min | 5 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Total | Coverage | Restarts | Status |
|---|---:|---:|---:|---|
| `iterate-2026-08-08-model-tier-review-opus` | 0.1 s | 0/5 | 0 | degraded |
| `iterate-2026-08-08-index-readers-adr-lock` | 98.0 min | 0/5 | 0 | degraded |
| `iterate-2026-08-08-triage-amend-event` | 402.4 min | 0/5 | 0 | degraded |
| `iterate-2026-08-08-mandated-load-truncation-report` | 6.2 min | 0/5 | 0 | degraded |
| `iterate-2026-08-08-prompt-scan-dynamic-import-fault-test` | 0.1 s | 0/5 | 0 | degraded |
| `iterate-2026-08-08-codex-operating-contract` | 19.3 min | 3/5 | 0 | degraded |
| `iterate-2026-08-08-retention-pins` | 14.4 min | 0/5 | 0 | degraded |
| `iterate-2026-08-08-six-small-defects` | 80.3 min | 3/5 | 0 | degraded |
| `iterate-2026-08-08-p2-52-shared-scripts-fixes` | 55.8 min | 0/5 | 0 | degraded |
| `iterate-2026-08-09-test-evidence-freshness-w3` | — | — | — | pre-instrumentation |
