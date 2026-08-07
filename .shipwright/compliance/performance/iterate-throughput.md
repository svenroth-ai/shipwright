# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the 5 groups that can — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-08-07-windows-ci-perf`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 0/5 fold-time-capturable groups (+2 derived), 47 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Total wall-clock (discovery through review):** 85.0 min
- **Unattributed:** 59.1 min (69.5%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of total)

| Phase | Inclusive | Exclusive | % of total |
|---|---:|---:|---:|
| discovery_diagnosis | *unattributed — no agent start/end marks recorded* | — | — |
| planning | 7.0 min *(derived — reconstructed from child spans)* | 5.3 min | 6.3% |
| implementation | *unattributed — no agent start/end marks recorded* | — | — |
| verification | 18.9 min *(derived — reconstructed from child spans)* | 3.5 min | 4.2% |
| review | *unattributed — no agent start/end marks recorded* | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| pre_f0_validation | verification | 0.1 s | completed | stage=f0 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 2.8 min | completed | capacity=22, stage=cpu, weight=11 |
| canonical_f0_active | verification | 6.9 min | completed | capacity=22, weight=11 |
| canonical_f0_active | verification | 5.7 min | completed | capacity=22, weight=11 |
| external_review | planning | 1.5 min | completed | provider=openrouter |
| external_review | planning | 12.6 s | completed | provider=openrouter |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | 3.9 min | 30.1 min | 3 |
| planning | 4.9 min | 719.5 min | 8 |
| implementation | 13.5 min | 20.1 min | 3 |
| verification | 3.5 min | 16.9 min | 7 |
| review | 3.1 min | 34.5 min | 7 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Total | Coverage | Restarts | Status |
|---|---:|---:|---:|---|
| `iterate-2026-08-06-triage-store-write-path` | 205.1 min | 0/5 | 0 | degraded |
| `iterate-2026-08-06-parallel-global-state-tests` | 169.9 min | 4/5 | 0 | degraded |
| `iterate-2026-08-05-adopt-derived-evidence-rollout` | 875.0 min | 1/5 | 0 | degraded |
| `iterate-2026-08-06-shared-read-run-config-mode-guard` | 95.6 min | 4/5 | 0 | degraded |
| `iterate-2026-08-06-resolve-run-id-seam` | 14.2 min | 0/5 | 0 | degraded |
| `iterate-2026-08-06-gc-decode-parity` | 112.6 min | 4/5 | 0 | degraded |
| `iterate-2026-08-06-triage-backlog-outbox-routing` | 95.1 min | 0/5 | 0 | degraded |
| `iterate-2026-08-07-test-phase-attribution` | 149.4 min | 1/5 | 0 | degraded |
| `iterate-2026-08-07-context-cost-meter` | 195.2 min | 0/5 | 0 | degraded |
| `iterate-2026-08-07-windows-ci-perf` | 85.0 min | 0/5 | 0 | degraded |
