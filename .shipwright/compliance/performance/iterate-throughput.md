# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the 5 groups that can — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-08-08-retention-pins`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 0/5 fold-time-capturable groups (+1 derived), 23 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Total wall-clock (discovery through review):** 14.4 min
- **Unattributed:** 0.0 s (0.0%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of total)

| Phase | Inclusive | Exclusive | % of total |
|---|---:|---:|---:|
| discovery_diagnosis | *unattributed — no agent start/end marks recorded* | — | — |
| planning | *unattributed — no agent start/end marks recorded* | — | — |
| implementation | *unattributed — no agent start/end marks recorded* | — | — |
| verification | 14.4 min *(derived — reconstructed from child spans)* | 23.9 s | 2.8% |
| review | *unattributed — no agent start/end marks recorded* | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| pre_f0_validation | verification | 0.1 s | completed | stage=f0 |
| f0_queue | verification | 0.0 s | completed | capacity=1, stage=warmup, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, stage=cpu, weight=11 |
| canonical_f0_active | verification | 14.0 min | completed | capacity=22, weight=11 |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 2.4 min | 4.1 min | 5 |
| implementation | 6.2 min | — | 1 |
| verification | 23.9 s | 159.4 min | 9 |
| review | 0.0 s | 0.8 s | 5 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Total | Coverage | Restarts | Status |
|---|---:|---:|---:|---|
| `iterate-2026-08-08-coverage-envelope-split` | 38.1 min | 0/5 | 0 | degraded |
| `iterate-2026-08-08-track-decision-drops` | 197.3 min | 0/5 | 0 | degraded |
| `iterate-2026-08-08-plan-reviewer-configurable` | 50.9 min | 0/5 | 0 | degraded |
| `iterate-2026-08-08-model-tier-review-opus` | 0.1 s | 0/5 | 0 | degraded |
| `iterate-2026-08-08-index-readers-adr-lock` | 98.0 min | 0/5 | 0 | degraded |
| `iterate-2026-08-08-triage-amend-event` | 402.4 min | 0/5 | 0 | degraded |
| `iterate-2026-08-08-mandated-load-truncation-report` | 6.2 min | 0/5 | 0 | degraded |
| `iterate-2026-08-08-prompt-scan-dynamic-import-fault-test` | 0.1 s | 0/5 | 0 | degraded |
| `iterate-2026-08-08-codex-operating-contract` | 19.3 min | 3/5 | 0 | degraded |
| `iterate-2026-08-08-retention-pins` | 14.4 min | 0/5 | 0 | degraded |
