# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-08-10-i2-test-evidence-phase-source-contract`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 0/5 applicable fold-time groups (+1 derived), 50 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Wall clock (scope through F5b):** — (missing_scope_mark)
- **Instrumented:** 226.3 min of wall clock (unavailable)
- **Unattributed:** 0.0 s (0.0%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of timing envelope)

| Phase | Inclusive | Exclusive | % of timing envelope |
|---|---:|---:|---:|
| discovery_diagnosis | *unattributed — no agent start/end marks recorded* | — | — |
| planning | *unattributed — no agent start/end marks recorded* | — | — |
| implementation | *unattributed — no agent start/end marks recorded* | — | — |
| verification | 226.3 min *(derived — reconstructed from child spans)* | 134.0 min | 59.2% |
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
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| canonical_f0_active | verification | 49.7 min | completed | capacity=22, weight=11 |
| canonical_f0_active | verification | 42.7 min | completed | capacity=22, weight=11 |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | 11.0 min | — | 1 |
| planning | 11.9 min | 19.2 min | 2 |
| implementation | 45.4 min | 69.4 min | 2 |
| verification | 11.5 min | 134.0 min | 9 |
| review | 1.3 min | 51.4 min | 4 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-08-08-p2-52-shared-scripts-fixes` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-08-09-test-evidence-freshness-w3` | — | — | — | — | pre-instrumentation |
| `iterate-2026-08-09-p2-56-amend-delivery-signal` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-08-09-timing-coverage` | 74.6 min | 100.0% | 4/4 | 0 | complete |
| `iterate-2026-08-09-dismissed-recurring` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-08-09-compaction-state-audit` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-08-09-token-cost-controllable` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-08-09-review-evidence-tier` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-08-09-p2-59-branch-feedback-authority` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-08-10-i2-test-evidence-phase-source-contract` | — | unavailable | 0/5 | 0 | degraded |
