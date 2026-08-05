# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the 5 groups that can — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-08-05-mirror-tree-drift-basis`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 0/5 fold-time-capturable groups (+1 derived), 6 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Total wall-clock (discovery through review):** 7.3 min
- **Unattributed:** 0.0 s (0.0%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of total)

| Phase | Inclusive | Exclusive | % of total |
|---|---:|---:|---:|
| discovery_diagnosis | *unattributed — no agent start/end marks recorded* | — | — |
| planning | *unattributed — no agent start/end marks recorded* | — | — |
| implementation | *unattributed — no agent start/end marks recorded* | — | — |
| verification | 7.3 min *(derived — reconstructed from child spans)* | 1.6 min | 22.6% |
| review | *unattributed — no agent start/end marks recorded* | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| pre_f0_validation | verification | 0.0 s | completed | stage=f0 |
| pre_f0_validation | verification | 0.0 s | completed | stage=f0 |
| f0_queue | verification | 0.0 s | completed | capacity=1, weight=1 |
| f0_queue | verification | 0.0 s | completed | capacity=22, weight=11 |
| canonical_f0_active | verification | 5.6 min | completed | capacity=22, weight=11 |

## Rolling comparison (last 2 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | 0.1 s | — | 1 |
| planning | 0.1 s | — | 1 |
| implementation | 19.4 min | — | 1 |
| verification | 1.6 min | — | 1 |
| review | 0.2 s | — | 1 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Total | Coverage | Restarts | Status |
|---|---:|---:|---:|---|
| `iterate-2026-08-05-by-commit-dedup-type-gate` | — | — | — | pre-instrumentation |
| `iterate-2026-08-05-worktree-evidence-recovery` | — | — | — | pre-instrumentation |
| `iterate-2026-08-05-prompt-scan-unicode-codespan` | — | — | — | pre-instrumentation |
| `iterate-2026-08-05-semver-prerelease-sort` | — | — | — | pre-instrumentation |
| `iterate-2026-08-05-f5b-dashboard-webui-unit-shape` | — | — | — | pre-instrumentation |
| `iterate-2026-08-05-bloat-baseline-vendored-hook` | — | — | — | pre-instrumentation |
| `iterate-2026-08-05-git-available-migration` | — | — | — | pre-instrumentation |
| `iterate-2026-08-05-risk-recheck-recording-integrity` | — | — | — | pre-instrumentation |
| `iterate-2026-08-05-iterate-timings-derived-parent` | 65.1 min | 4/5 | 0 | degraded |
| `iterate-2026-08-05-mirror-tree-drift-basis` | 7.3 min | 0/5 | 0 | degraded |
