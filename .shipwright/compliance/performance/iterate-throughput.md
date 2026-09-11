# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-09-11-pr-review-evidence-filter-gap`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 1/4 applicable fold-time groups (+2 derived), 30 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Wall clock (scope through F5b):** 75.0 min (measured)
- **Instrumented:** 47.1 min of wall clock (62.8%)
- **Unattributed:** 27.9 min (37.2%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of timing envelope)

| Phase | Inclusive | Exclusive | % of timing envelope |
|---|---:|---:|---:|
| discovery_diagnosis | *not applicable — planning is the recorded entry path* | — | — |
| planning | 11.8 min *(derived — reconstructed from child spans)* | 10.0 min | 15.4% |
| implementation | 25.6 min | 25.6 min | 39.4% |
| verification | 20.2 min *(derived — reconstructed from child spans)* | 1.2 s | 0.0% |
| review | *incomplete* (started, not closed) | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| canonical_f0_active | verification | 20.2 min | completed | capacity=22, weight=11 |
| self_review | review | — | incomplete | — |
| external_review | planning | 37.8 s | completed | provider=codex |
| external_review | planning | 43.7 s | completed | provider=codex |
| external_review | planning | 24.5 s | completed | provider=codex |
| external_review | review | 1.3 min | completed | provider=codex |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 2.7 min | 24.1 min | 6 |
| implementation | 16.1 min | 51.8 min | 8 |
| verification | 17.7 s | 12.2 min | 8 |
| review | 2.1 min | 4.2 min | 2 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-09-10-pr-review-generated-only` | 92.8 min | 65.7% | 1/5 | 0 | degraded |
| `iterate-2026-09-10-keystone-verifier-sensitive-path` | 41.5 min | 66.8% | 1/5 | 0 | degraded |
| `iterate-2026-09-10-keystone-detective-arm` | 96.8 min | 47.1% | 1/4 | 0 | degraded |
| `iterate-2026-09-10-p34c-promotion-anchor-guard` | 196.9 min | 26.1% | 1/5 | 0 | degraded |
| `iterate-2026-09-11-e0-ledger-accounting` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-11-t0-seam-survey` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-11-binding-completeness-rollout-transition` | 69.0 min | 88.2% | 1/4 | 0 | degraded |
| `iterate-2026-09-11-ac-ratchet-push-observe` | 111.7 min | 53.0% | 1/5 | 0 | degraded |
| `iterate-2026-09-10-triage-cross-tree-precedence` | 154.9 min | 74.7% | 1/4 | 0 | degraded |
| `iterate-2026-09-11-pr-review-evidence-filter-gap` | 75.0 min | 62.8% | 1/4 | 0 | degraded |
