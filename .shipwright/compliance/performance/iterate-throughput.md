# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-09-21-orphan-evidence-cleanup`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 0/5 applicable fold-time groups (+1 derived), 45 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Wall clock (scope through F5b):** 51.7 min (measured)
- **Instrumented:** 45.8 min of wall clock (88.5%)
- **Unattributed:** 5.9 min (11.5%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of timing envelope)

| Phase | Inclusive | Exclusive | % of timing envelope |
|---|---:|---:|---:|
| discovery_diagnosis | *unattributed — no agent start/end marks recorded* | — | — |
| planning | *unattributed — no agent start/end marks recorded* | — | — |
| implementation | *incomplete* (started, not closed) | — | — |
| verification | 45.8 min *(derived — reconstructed from child spans)* | 2.3 min | 5.0% |
| review | *unattributed — no agent start/end marks recorded* | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| pre_f0_validation | verification | 0.0 s | completed | stage=f0 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| canonical_f0_active | verification | 21.2 min | completed | capacity=22, weight=11 |
| canonical_f0_active | verification | 22.2 min | completed | capacity=22, weight=11 |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 3.4 min | 50.6 min | 6 |
| implementation | 42.1 min | 209.2 min | 6 |
| verification | 22.1 s | 35.2 min | 10 |
| review | 15.6 min | — | 1 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-09-16-deploy-ac02-ac05-coded-gates` | 110.6 min | 45.3% | 0/5 | 0 | degraded |
| `iterate-2026-09-16-opus-review-leg-codex-driver` | 623.4 min | 37.3% | 1/4 | 0 | degraded |
| `iterate-2026-09-13-codex-internal-review-transport` | 267.1 min | 15.8% | 1/4 | 0 | degraded |
| `iterate-2026-09-18-codex-review-tier-config` | 283.4 min | 29.1% | 1/4 | 0 | degraded |
| `iterate-2026-09-19-codex-reviewer-session-override` | 90.6 min | 74.7% | 1/5 | 0 | degraded |
| `iterate-2026-09-19-e2e-journey-coverage-gate` | 527.2 min | 19.4% | 0/4 | 0 | degraded |
| `iterate-2026-09-20-r0-resolve-1a-envelope-delivery` | 140.5 min | 19.8% | 0/4 | 0 | degraded |
| `iterate-2026-09-20-shared-rollout-commit-resolver` | 39.6 min | 19.4% | 1/5 | 0 | degraded |
| `iterate-2026-09-20-m4-codex-subagent-dispatch` | 160.3 min | 74.7% | 1/4 | 0 | degraded |
| `iterate-2026-09-21-orphan-evidence-cleanup` | 51.7 min | 88.5% | 0/5 | 0 | degraded |
