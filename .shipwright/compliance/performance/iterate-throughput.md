# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-09-10-pr-review-generated-only`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 1/5 applicable fold-time groups (+1 derived), 47 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Wall clock (scope through F5b):** 92.8 min (measured)
- **Instrumented:** 60.9 min of wall clock (65.7%)
- **Unattributed:** 31.8 min (34.3%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of timing envelope)

| Phase | Inclusive | Exclusive | % of timing envelope |
|---|---:|---:|---:|
| discovery_diagnosis | *unattributed — no agent start/end marks recorded* | — | — |
| planning | *unattributed — no agent start/end marks recorded* | — | — |
| implementation | 7.5 min | 7.5 min | 8.8% |
| verification | 52.4 min *(derived — reconstructed from child spans)* | 4.2 min | 4.9% |
| review | *incomplete* (started, not closed) | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| pre_f0_validation | verification | 0.0 s | completed | stage=f0 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| canonical_f0_active | verification | 24.6 min | completed | capacity=22, weight=11 |
| canonical_f0_active | verification | 23.5 min | completed | capacity=22, weight=11 |
| self_review | review | — | incomplete | — |
| external_review | review | 1.0 min | completed | provider=codex |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 0.0 s | 0.0 s | 4 |
| implementation | 29.6 min | 32.1 min | 3 |
| verification | 42.5 s | 4.2 min | 7 |
| review | 0.0 s | 0.0 s | 2 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-09-09-s1-dashboard-phase-strip` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-09-09-p4-1-glossary-generator` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-09-09-s2-adopted-config-shape` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-09-09-s2b-backfill-existing-adopted-config` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-09-09-p3-6-keystone-gate` | — | — | — | — | pre-instrumentation |
| `iterate-2026-09-10-s3-hooks-and-state` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-10-s4-verifiers-and-converter` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-10-s5-retarget-v1-then-drop` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-10-p4-2-grill-trace-gate` | — | — | — | — | pre-instrumentation |
| `iterate-2026-09-10-pr-review-generated-only` | 92.8 min | 65.7% | 1/5 | 0 | degraded |
