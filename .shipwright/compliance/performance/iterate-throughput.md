# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-09-06-fr-hygiene-touched-rows`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 1/5 applicable fold-time groups (+1 derived), 29 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Wall clock (scope through F5b):** 157.1 min (measured)
- **Instrumented:** 45.4 min of wall clock (28.9%)
- **Unattributed:** 111.8 min (71.1%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of timing envelope)

| Phase | Inclusive | Exclusive | % of timing envelope |
|---|---:|---:|---:|
| discovery_diagnosis | *unattributed — no agent start/end marks recorded* | — | — |
| planning | *unattributed — no agent start/end marks recorded* | — | — |
| implementation | 33.2 min | 33.2 min | 23.2% |
| verification | 5.2 min *(derived — reconstructed from child spans)* | 17.0 s | 0.2% |
| review | *incomplete* (started, not closed) | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| pre_f0_validation | verification | 0.0 s | completed | stage=f0 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| canonical_f0_active | verification | 4.9 min | completed | capacity=22, weight=11 |
| self_review | review | — | incomplete | — |
| external_review | review | 5.6 min | completed | provider=codex |
| external_review | planning | 55.2 s | completed | provider=codex |
| external_review | planning | 27.2 s | completed | provider=codex |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 49.3 s | 2.4 min | 3 |
| implementation | 17.6 min | 102.4 min | 8 |
| verification | 15.7 s | 911.1 min | 8 |
| review | — | — | 0 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-08-31-pr-review-deepseek-model` | 86.6 min | 29.8% | 1/4 | 0 | degraded |
| `iterate-2026-09-01-changelog-config-marketplace-sync` | 60.9 min | 12.2% | 1/5 | 0 | degraded |
| `iterate-2026-09-01-external-review-retry-degradation` | 80.3 min | 44.8% | 1/5 | 0 | degraded |
| `iterate-2026-09-02-glm-plan-code-review-swap` | 147.5 min | 39.6% | 1/5 | 0 | degraded |
| `iterate-2026-09-03-codex-cli-review-leg` | 145.2 min | 74.3% | 1/4 | 0 | degraded |
| `iterate-2026-09-03-pr-review-block-visibility` | 7.0 min | 22.9% | 1/5 | 0 | degraded |
| `iterate-2026-09-03-pr-review-sonnet-default` | 16.9 min | 0.0% | 0/5 | 0 | degraded |
| `iterate-2026-09-03-review-scratch-path` | 1491.5 min | 63.1% | 0/4 | 0 | degraded |
| `iterate-2026-09-05-codex-availability-probe-flags` | 25.2 min | 20.6% | 1/5 | 0 | degraded |
| `iterate-2026-09-06-fr-hygiene-touched-rows` | 157.1 min | 28.9% | 1/5 | 0 | degraded |
