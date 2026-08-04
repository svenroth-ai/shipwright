# Mini-Plan — Restore F0 Fleet Throughput and Stabilize Suite Concurrency

**Run ID:** `iterate-2026-08-04-f0-fleet-throughput`

## Files to create or modify

- `shipwright_test_config.json` — explicit measured per-run budget and safe integration
  scheduling policy.
- `shared/scripts/tools/run_test_suite.py` — cancellation wiring, lifecycle progress,
  bounded diagnostics publication, and retained gate/retry semantics.
- `shared/scripts/tools/suite_process.py` (new) — bounded-output child supervisor with
  Windows Job Object termination/reaping and POSIX process-group parity.
- `shared/scripts/tools/suite_process_child.py` (new) — Windows handshake launcher that
  cannot spawn uv until its parent assigns it to the Job Object.
- `shared/scripts/tools/suite_diagnostics.py` (new) — bounded, run-scoped diagnostic
  evidence writer and path returned to race follow-ups.
- `shared/scripts/tools/suite_budget.py` — cancellation-aware pool shutdown and bounded
  active/queued heartbeat state.
- `shared/scripts/tools/suite_race_triage.py` / `suite_report.py` — link private
  run-scoped evidence without copying failure output into tracked triage.
- `shared/scripts/tools/tests/test_run_test_suite_faults.py` — timeout, diagnostic tail,
  cancellation, and cleanup regressions.
- `shared/scripts/tools/tests/test_suite_host_resources.py` — lifecycle progress,
  lease-release, and scheduling-policy tests.
- `shared/scripts/tools/tests/test_host_resource_lease_process.py` — synchronized
  overlap/FIFO probes replacing fixed launch-time thresholds.
- `shared/scripts/tools/tests/test_suite_diagnostics.py` (new) — bounded JSON
  round-trip/path/collision tests.
- `integration-tests/` — only a scheduling/CI-parity regression if config-level proof
  cannot live in the shared tools root; no production cache behavior change.
- `plugins/shipwright-iterate/skills/iterate/references/F0.md`,
  `docs/hooks-and-pipeline.md`, and `docs/guide.md` — test-infrastructure contract,
  progress, cleanup, evidence, and measured fleet-budget rationale.
- run-specific changelog, decision, review, and F5c evidence artifacts.

## Work breakdown

1. Persist the pre-fix whole-suite timings/failure summaries. After the fix, collect
   three canonical timing sets and replay weights 8, 11, and 22 against four simultaneous
   arrivals. Select by completed-runs/hour, then lower mean/max queue, then smaller
   weight on a tie; record capacity and integration policy.
2. Write RED tests for explicit scheduling policy, synchronized lease ordering, bounded
   lifecycle lines, bounded diagnostic tails, timeout/cancellation descendant cleanup,
   lease release, and immediate next-run cleanliness.
3. Replace elapsed-time lease assertions with process gates and validate by mutation
   that overlap/FIFO regressions still turn the tests red.
4. Implement the platform supervisor. On Windows start a launcher blocked on a pipe,
   assign it to a kill-on-close Job Object, then release it to spawn uv; on POSIX start
   uv in a new session. Continuously drain combined bytes into a fixed-size in-memory
   tail and publish only that bounded tail to the attempt file; decode it only after
   termination, reap, and retain `(rc, output, seconds, pytest_ran)`.
   JUnit existence, never output text, remains the classifier proof.
5. Make the outer executor cancellation-aware; emit unit queued/start/completion and
   retry lifecycle lines while retaining periodic heartbeats and result ordering.
6. Redact known credential shapes, mark tails untrusted, encode/cap path components, and
   atomically write bounded run-scoped evidence before attempt directories are removed.
   Pass only its relative path to race triage; a write failure cannot replace a red test.
7. Apply the measured budget/integration policy; repeat the controlled whole suite,
   targeted roots, native Windows probes, review cascade, canonical F0, lint, local CI
   guards, finalization, and delivery.

## Test strategy

- Unit: scheduler/config parsing, lifecycle rendering, tail cap/truncation, evidence
  serialization, exit precedence, retry shape, and cancellation signalling.
- Real subprocess: uv-like parent with pytest-like child and persistent grandchild;
  timeout, cancellation, and an intermediate-parent exit must remove all descendants
  and preserve the redacted tail.
- Concurrency: sibling git worktree leases with explicit release gates and state-order
  assertions; no correctness assertion depends on process startup occurring in <1 s.
- Composition: integration root alone with xdist, alone serially, and repeatedly through
  the whole outer pool; tools root alone and through the same whole-suite runs.
- Full: repeated canonical F0 with Git Bash available, then CI-parity and coverage gates.

## Alternative considered

Raising timeouts or simply retrying more was rejected: it preserves the nested resource
oversubscription, turns scheduling delay into longer queue latency, leaves cancellation
descendants alive, and still loses the original failure evidence. Disabling all xdist
globally was also rejected because it discards proven safe throughput from `shared/tests`.
