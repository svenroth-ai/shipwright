# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the 5 groups that can — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-08-06-architecture-review-pass`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 0/5 fold-time-capturable groups (+1 derived), 2 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Total wall-clock (discovery through review):** 0.0 s
- **Unattributed:** 0.0 s (0.0%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of total)

| Phase | Inclusive | Exclusive | % of total |
|---|---:|---:|---:|
| discovery_diagnosis | *unattributed — no agent start/end marks recorded* | — | — |
| planning | *unattributed — no agent start/end marks recorded* | — | — |
| implementation | *unattributed — no agent start/end marks recorded* | — | — |
| verification | 0.0 s *(derived — reconstructed from child spans)* | 0.0 s | 0.0% |
| review | *unattributed — no agent start/end marks recorded* | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| pre_f0_validation | verification | 0.0 s | completed | stage=f0 |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 0.0 s | 7.9 min | 3 |
| implementation | 18.9 min | — | 1 |
| verification | 15.0 s | 1.9 min | 9 |
| review | 0.0 s | 63.1 min | 5 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Total | Coverage | Restarts | Status |
|---|---:|---:|---:|---|
| `iterate-2026-08-05-run-suite-console-encoding-guard` | 12.0 min | 0/5 | 0 | degraded |
| `iterate-2026-08-05-iterate-entry-tail-fallback-fail-closed` | 35.5 min | 0/5 | 0 | degraded |
| `iterate-2026-08-05-mirror-tree-drift-basis` | 7.3 min | 0/5 | 0 | degraded |
| `iterate-2026-08-05-prompt-scan-dynamic-import-fp` | 7.4 min | 0/5 | 0 | degraded |
| `iterate-2026-08-05-triage-launch-payload-cli` | 2.6 min | 0/5 | 0 | degraded |
| `iterate-2026-08-05-split-iterate-entry-tail-fallback-tests` | 5.2 min | 0/5 | 0 | degraded |
| `iterate-2026-08-05-llm-review-gateway-route` | 26.1 min | 0/5 | 0 | degraded |
| `iterate-2026-08-05-inline-suppression-ratchet` | 89.9 min | 3/5 | 0 | degraded |
| `iterate-2026-08-05-wire-local-guard-scripts` | 103.6 min | 0/5 | 0 | degraded |
| `iterate-2026-08-06-architecture-review-pass` | 0.0 s | 0/5 | 0 | degraded |
