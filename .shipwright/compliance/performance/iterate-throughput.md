# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-08-26-campaign-worktree-guard-followups`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 1/4 applicable fold-time groups (+2 derived), 28 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Wall clock (scope through F5b):** 130.2 min (measured)
- **Instrumented:** 114.9 min of wall clock (88.3%)
- **Unattributed:** 15.2 min (11.7%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of timing envelope)

| Phase | Inclusive | Exclusive | % of timing envelope |
|---|---:|---:|---:|
| discovery_diagnosis | *not applicable — planning is the recorded entry path* | — | — |
| planning | 3.1 min *(derived — reconstructed from child spans)* | 0.0 s | 0.0% |
| implementation | 109.9 min | 109.9 min | 90.0% |
| verification | 5.0 min *(derived — reconstructed from child spans)* | 6.0 s | 0.1% |
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
| external_review | planning | 3.1 min | completed | provider=openrouter |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 0.0 s | 3.0 min | 5 |
| implementation | 45.2 min | 109.9 min | 6 |
| verification | 28.2 s | 45.9 min | 8 |
| review | 0.0 s | — | 1 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-08-25-R0-spec-reader-shipped-shape` | 71.4 min | 0.0% | 0/5 | 0 | degraded |
| `iterate-2026-08-25-r0-spec-reader-shipped-shape` | 77.6 min | 0.0% | 0/5 | 0 | degraded |
| `iterate-2026-08-25-r1a-evidence-staging-multiroot` | 108.2 min | 3.4% | 0/4 | 0 | degraded |
| `iterate-2026-08-25-fr-criteria-parser-pin` | 43.8 min | 88.3% | 1/5 | 0 | degraded |
| `iterate-2026-08-25-campaign-run-id-lowercase-mint` | 45.0 min | 62.0% | 1/5 | 0 | degraded |
| `iterate-2026-08-25-a-widen-the-net` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-08-26-campaign-worktree-guard` | 85.6 min | 86.5% | 1/5 | 0 | degraded |
| `iterate-2026-08-26-r1b-ci-manifest-regen-gate` | 375.3 min | 33.5% | 1/4 | 0 | degraded |
| `iterate-2026-08-26-b-pure-hardening` | — | — | — | — | pre-instrumentation |
| `iterate-2026-08-26-campaign-worktree-guard-followups` | 130.2 min | 88.3% | 1/4 | 0 | degraded |
