# Iterate throughput

> Derived report — reproducible entirely from `shipwright_events.jsonl`. Not an agent startup input; regenerated at F5b. A missing applicable agent mark is shown as *unattributed* with a reason, never as zero duration; the two structurally-limited groups (`finalization`, `delivery`) are labeled separately — see the Coverage boundary note below.

> **Derived spans:** a fold-time-capturable group with no agent start/end mark, but at least one producer child that names it as parent, is reconstructed from that child's own envelope and shown labeled *derived* rather than left unattributed — real duration data, not a measured boundary; it does not count toward coverage.

> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 commits and F11 delivers — `discovery_diagnosis` through `review` can close by then, but `finalization`'s own duration and the entire `delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) structurally cannot, in every run. Coverage below is measured against the four applicable groups when one entry path is recorded; a run that explicitly records both `discovery_diagnosis` and `planning` is measured against all five — see `iterate-timings.md` for why.

## Latest run: `iterate-2026-09-24-r5b-merge-lane`

- **Timing source:** producer + agent spans (mixed) · **coverage:** 1/4 applicable fold-time groups (+1 derived), 6 spans total — **DEGRADED** (a fold-time-capturable phase is missing)
- **Wall clock (scope through F5b):** 73.8 min (measured)
- **Instrumented:** 40.3 min of wall clock (54.6%)
- **Unattributed:** 33.5 min (45.4%)
- **Invalidation-driven restarts:** 0

### Top-level phases (inclusive / exclusive / % of timing envelope)

| Phase | Inclusive | Exclusive | % of timing envelope |
|---|---:|---:|---:|
| discovery_diagnosis | *not applicable — planning is the recorded entry path* | — | — |
| planning | 50.4 s *(derived — reconstructed from child spans)* | 0.0 s | 0.0% |
| implementation | 38.8 min | 38.8 min | 100.0% |
| verification | *unattributed — no agent start/end marks recorded* | — | — |
| review | *incomplete* (started, not closed) | — | — |
| finalization | *not reached before F5b fold (structural)* | — | — |
| delivery | *not reached before F5b fold (structural)* | — | — |

### Nested spans

| Span | Parent | Duration | Outcome | Detail |
|---|---|---:|---|---|
| self_review | review | — | incomplete | — |
| external_review | planning | 50.4 s | completed | provider=codex |
| external_review | review | 1.6 min | completed | provider=codex |

## Rolling comparison (last 10 instrumented runs)

| Phase | Median exclusive | P90 exclusive | Samples |
|---|---:|---:|---:|
| discovery_diagnosis | — | — | 0 |
| planning | 0.0 s | 0.0 s | 4 |
| implementation | 52.4 min | 348.9 min | 6 |
| verification | 2.3 min | 51.9 min | 7 |
| review | 0.0 s | — | 1 |
| finalization | — | — | 0 |
| delivery | — | — | 0 |

## Run history

| Run | Wall | Instrumented | Group coverage | Restarts | Status |
|---|---:|---:|---:|---:|---|
| `iterate-2026-09-21-r1-depends-on-schema` | — | unavailable | 0/5 | 0 | degraded |
| `iterate-2026-09-22-r2-worktree-capability` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-22-r1b-codex-hooks-config-layer-shim` | 792.3 min | 24.2% | 1/4 | 0 | degraded |
| `iterate-2026-09-22-r3-review-diff-fix` | — | unavailable | 0/4 | 0 | degraded |
| `iterate-2026-09-22-r4-state-mechanics` | 112.3 min | 49.8% | 1/5 | 0 | degraded |
| `iterate-2026-09-20-r2-m3-hook-parity-iterate-only` | 1054.9 min | 37.3% | 1/5 | 0 | degraded |
| `iterate-2026-09-23-codextender-monorepo-part-c` | 147.1 min | 65.5% | 1/5 | 0 | degraded |
| `iterate-2026-09-23-codextender-part-c-bloat-split` | — | — | — | — | pre-instrumentation |
| `iterate-2026-09-23-r5a-wave-build-flip` | 89.8 min | 57.7% | 1/5 | 0 | degraded |
| `iterate-2026-09-24-r5b-merge-lane` | 73.8 min | 54.6% | 1/4 | 0 | degraded |
