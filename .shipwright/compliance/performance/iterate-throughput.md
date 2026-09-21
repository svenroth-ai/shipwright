# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-09-11-glossary-p41-review-followups`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 1/5 applicable fold-time groups (+1 derived), 27 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Wall clock (scope through F5b):** 86.8 min (measured)
- **Instrumented:** 52.5 min of wall clock (60.4%)
- **Unattributed:** 34.4 min (39.6%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of timing envelope)

| Phase | Inclusive | Exclusive | % of timing envelope |
|---|---:|---:|---:|
| discovery_diagnosis | *unattributed — no agent start/end marks recorded* | — | — |
| planning | *unattributed — no agent start/end marks recorded* | — | — |
| implementation | 18.2 min | 18.2 min | 26.1% |
| verification | 33.3 min *(derived — reconstructed from child spans)* | 18.9 s | 0.5% |
| review | *incomplete* (started, not closed) | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| pre_f0_validation | verification | 0.1 s | completed | stage=f0 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 5.1 min | completed | capacity=22, stage=cpu, weight=11 |
| canonical_f0_active | verification | 27.9 min | completed | capacity=22, weight=11 |
| self_review | review | — | incomplete | — |
| external_review | review | 1.0 min | completed | provider=codex |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 0.0 s | 1.9 min | 5 |
| implementation | 18.2 min | 29.7 min | 5 |
| verification | 18.9 s | 4.2 min | 7 |
| review | 0.0 s | 0.0 s | 3 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-09-10-s5-retarget-v1-then-drop` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-10-p4-2-grill-trace-gate` | — | — | — | — | pre-instrumentation |
| `iterate-2026-09-10-p4-3-elicitation-site-discovery` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-10-p4-4-grill-module-recent-rules-drift` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-09-10-p3-7-feeder-checks-anti-ratcheted` | — | — | — | — | pre-instrumentation |
| `iterate-2026-09-10-pr-review-generated-only` | 92.8 min | 65.7% | 1/5 | 0 | degraded |
| `iterate-2026-09-10-keystone-verifier-sensitive-path` | 41.5 min | 66.8% | 1/5 | 0 | degraded |
| `iterate-2026-09-10-keystone-detective-arm` | 96.8 min | 47.1% | 1/4 | 0 | degraded |
| `iterate-2026-09-10-p34c-promotion-anchor-guard` | 196.9 min | 26.1% | 1/5 | 0 | degraded |
| `iterate-2026-09-11-glossary-p41-review-followups` | 86.8 min | 60.4% | 1/5 | 0 | degraded |
