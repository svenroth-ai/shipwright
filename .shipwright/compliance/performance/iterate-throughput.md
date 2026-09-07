# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-09-07-p3-4-tagging-backfill`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 0/4 applicable fold-time groups (+2 derived), 65 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Wall clock (scope through F5b):** — (missing_scope_mark)
- **Instrumented:** 82.2 min of wall clock (unavailable)
- **Unattributed:** 75.0 min (47.7%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of timing envelope)

| Phase | Inclusive | Exclusive | % of timing envelope |
|---|---:|---:|---:|
| discovery_diagnosis | *not applicable — planning is the recorded entry path* | — | — |
| planning | 3.3 min *(derived — reconstructed from child spans)* | 0.0 s | 0.0% |
| implementation | *unattributed — no agent start/end marks recorded* | — | — |
| verification | 78.9 min *(derived — reconstructed from child spans)* | 16.8 min | 10.7% |
| review | *unattributed — no agent start/end marks recorded* | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| canonical_f0_active | verification | 20.2 min | completed | capacity=22, weight=11 |
| canonical_f0_active | verification | 20.3 min | completed | capacity=22, weight=11 |
| canonical_f0_active | verification | 21.6 min | completed | capacity=22, weight=11 |
| external_review | planning | 3.3 min | completed | provider=codex |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 0.0 s | 0.0 s | 3 |
| implementation | 19.5 min | 99.2 min | 4 |
| verification | 21.6 s | 16.7 min | 10 |
| review | 0.0 s | — | 1 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-09-06-fr-hygiene-touched-rows` | 157.1 min | 28.9% | 1/5 | 0 | degraded |
| `iterate-2026-09-06-lighthouse-perf-lockfile-bump` | 9.3 min | 39.7% | 1/5 | 0 | degraded |
| `iterate-2026-09-06-post-679-hygiene-sweep` | 33.6 min | 78.1% | 1/5 | 0 | degraded |
| `iterate-2026-09-06-reconcile-fr-01-18` | 29.5 min | 69.6% | 0/5 | 0 | degraded |
| `iterate-2026-09-06-p3-1-ac-identity-reader-corpus` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-06-triage-cross-tree-pending-delivery` | 167.0 min | 85.0% | 1/5 | 0 | degraded |
| `iterate-2026-09-06-ts-repair-safety-unsupported` | 234.0 min | 8.8% | 0/5 | 0 | degraded |
| `iterate-2026-09-07-p3-2-tag-grammar-manifest-v4` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-09-07-p3-3-producers-emit-and-require-binding` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-07-p3-4-tagging-backfill` | — | unavailable | 0/4 | 0 | degraded |
