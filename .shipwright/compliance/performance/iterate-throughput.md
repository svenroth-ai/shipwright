# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-09-02-glm-plan-code-review-swap`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 1/5 applicable fold-time groups (+1 derived), 28 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Wall clock (scope through F5b):** 147.5 min (measured)
- **Instrumented:** 58.4 min of wall clock (39.6%)
- **Unattributed:** 89.1 min (60.4%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of timing envelope)

| Phase | Inclusive | Exclusive | % of timing envelope |
|---|---:|---:|---:|
| discovery_diagnosis | *unattributed — no agent start/end marks recorded* | — | — |
| planning | *unattributed — no agent start/end marks recorded* | — | — |
| implementation | 52.1 min | 52.1 min | 57.7% |
| verification | 4.9 min *(derived — reconstructed from child spans)* | 8.6 s | 0.2% |
| review | *incomplete* (started, not closed) | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| pre_f0_validation | verification | 0.0 s | completed | stage=f0 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| canonical_f0_active | verification | 4.7 min | completed | capacity=22, weight=11 |
| self_review | review | — | incomplete | — |
| external_review | review | 39.6 s | completed | provider=openrouter |
| external_review | review | 41.2 s | completed | provider=openrouter |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 24.6 s | 49.3 s | 2 |
| implementation | 17.6 min | 109.9 min | 9 |
| verification | 7.3 s | 19.4 s | 10 |
| review | — | — | 0 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-08-26-campaign-worktree-guard-followups` | 130.2 min | 88.3% | 1/4 | 0 | degraded |
| `iterate-2026-08-27-fr-table-titlecols-split` | 25.9 min | 18.6% | 1/5 | 0 | degraded |
| `iterate-2026-08-27-s2b-discovery-c` | 87.5 min | 57.6% | 1/5 | 0 | degraded |
| `iterate-2026-08-28-changelog-encoding-cp1252` | 20.0 min | 48.8% | 1/5 | 0 | degraded |
| `iterate-2026-08-29-compliance-interpreter-fix` | 49.4 min | 0.0% | 0/5 | 0 | degraded |
| `iterate-2026-08-31-compliance-error-surfacing` | 55.0 min | 41.2% | 1/5 | 0 | degraded |
| `iterate-2026-08-31-pr-review-deepseek-model` | 86.6 min | 29.8% | 1/4 | 0 | degraded |
| `iterate-2026-09-01-changelog-config-marketplace-sync` | 60.9 min | 12.2% | 1/5 | 0 | degraded |
| `iterate-2026-09-01-external-review-retry-degradation` | 80.3 min | 44.8% | 1/5 | 0 | degraded |
| `iterate-2026-09-02-glm-plan-code-review-swap` | 147.5 min | 39.6% | 1/5 | 0 | degraded |
