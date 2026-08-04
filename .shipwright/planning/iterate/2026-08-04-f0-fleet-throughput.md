# Restore F0 Fleet Throughput and Stabilize Suite Concurrency

- **Run ID:** `iterate-2026-08-04-f0-fleet-throughput`
- **Status:** draft
- **Intent:** bug
- **Complexity:** medium
- **Spec impact:** NONE — this restores the framework's existing F0 scheduling,
  observability, cleanup, and evidence contracts; it changes no adopted product FR.

## Problem

P1.12 made F0 host-safe, but an absent `suite.max_workers` makes every sibling
request the entire 22-CPU host lease, so otherwise compatible F0 runs queue in a
single-file line. The runner also capture-buffers each unit, exposes no bounded
unit lifecycle stream, and relies on `subprocess.run(timeout=...)`; on Windows that
kills only the direct uv process, discards captured timeout output, and has no
contract to cancel and reap pytest/xdist descendants before releasing leases and
temporary/coverage state.

The first controlled whole-suite run reproduced both recorded race shapes. The
xdist-allowlisted `integration-tests` unit failed 17 cache-fanout tests under the
outer fleet load, then passed serially; the same root passed 468/468 alone with
xdist still enabled. `shared/scripts/tools/tests` failed three host-lease ordering
tests under the outer pool and passed 446/446 alone. Those tests use fixed
sub-second wall-clock holds as a proxy for overlap/FIFO, so host scheduling delay
is mistaken for a locking defect.

## Scope

One cohesive runner-level correction:

1. choose and document a bounded per-run CPU budget from replayed whole-suite unit
   timings, aggregate four-run fleet throughput, and queue time; retain the P1.12
   weighted host lease so total granted weight cannot exceed host capacity. The
   predeclared candidates are weights 8, 11, and 22: 8 preserves the largest retained
   xdist fan-out, 11 is the largest request for two simultaneous runs on this host,
   and 22 is the current serial baseline. Three final whole-suite timing samples feed
   the replay; ties prefer the smaller weight;
2. remove `integration-tests` from the xdist allowlist so the actual pytest command
   is serial inside that unit. Its own explicit subprocess fan-out remains tested,
   but only one such integration test executes at a time while the outer pool retains
   concurrency. Keep `shared/tests` at xdist 8;
3. replace timing-threshold lease tests with explicitly synchronized process-order
   probes that still falsify overlap and FIFO regressions under load;
4. emit bounded unit queued/start/completion/retry progress and periodic heartbeats;
5. on timeout or cancellation, terminate and reap the complete child tree, retain a
   bounded diagnostic tail in run-scoped evidence, and prove the next run can reuse
   temp, coverage, and host leases.

Out of scope: CI parallelism, a new test shard model, changing gate precedence,
weakening coverage, changing the one-test-root rule, or repairing unrelated tests.

## Root Causes

1. `normalize_cpu_weight(None)` returns host capacity. With no configured
   `suite.max_workers`, every F0 asks for weight 22; strict FIFO correctly serializes
   them, but fleet throughput collapses.
2. `integration-tests` combines xdist workers with tests that themselves fan out up
   to twelve subprocesses. Under the full outer pool this nested fan-out exhausts
   scheduling headroom and crosses cache-ready deadlines; alone with xdist it is
   green, and alone serially it is green.
3. The three outer-only lease failures assert fixed elapsed gaps while their probe
   processes are unsynchronized. CPU/process-start delay can outlast the holder's
   sleep, so correct locking is reported as failed overlap or FIFO bypass.
4. `subprocess.run(timeout=...)` owns only the uv child. Its Windows timeout path does
   not provide descendant-tree cancellation, and `_exec` replaces `TimeoutExpired`
   (including captured output) with one generic line. A parent `KeyboardInterrupt`
   waits for executor workers instead of signalling them to kill their trees.

## Acceptance Criteria

1. A run requests an explicit positive budget below 22, and two sibling F0 CPU
   leases acquire concurrently while total live granted weight never exceeds 22.
2. The selected budget is backed by a run-specific replay of three measured final
   whole-suite duration sets for candidates 8, 11, and 22, comparing four-run fleet
   makespan, completed-runs/hour, mean queue time, and maximum queue time. The evidence
   records host capacity and integration policy; ties prefer the smaller request.
3. The integration root is absent from `suite.xdist`, its launched command contains no
   `-n`/`--numprocesses`, and it is stable in repeated controlled whole-suite runs.
4. The outer-only host-lease tests prove overlap and FIFO through explicit process
   gates/order, not fixed sub-second launch timing, and fail under planted ordering
   regressions.
5. Each unit emits ASCII-safe, bounded queued/start/completion lines with run id,
   unit id, weight, outcome, and elapsed time; retries name their authoritative or
   same-shape state, and periodic heartbeats remain.
6. Unit stdout/stderr capture is bounded and is not consulted for classification
   (JUnit existence remains the independent pytest-ran proof). A timeout/failure
   retains a deterministic byte-capped tail with UTF-8 replacement, truncation
   disclosure, conservative credential redaction, and an `untrusted` label in a
   run-scoped gitignored evidence artifact. A race card links that artifact without
   embedding output in tracked triage data.
7. On Windows a handshake-blocked launcher is assigned to a kill-on-close Job Object
   before it can spawn uv; timeout, cancellation, and normal-exit cleanup terminate any
   remaining job descendants and reap the launcher before `_exec` returns. A native
   probe covers uv, pytest, xdist-like workers, and a grandchild whose intermediate
   parent exits. POSIX uses a new session/process group with bounded TERM-to-KILL parity.
8. One run-scoped cancellation event stops new in-process budget admission and signals
   every active supervisor before executor shutdown. The host lease wait remains
   interrupt-safe through its existing context manager, and the coverage lock remains
   non-blocking/handle-owned. Cancellation unwinds pool, CPU lease, and coverage lock;
   an immediate next invocation can acquire them and reset only this run's namespaced
   temp/coverage state without touching a live sibling.
9. Existing strict exit precedence, JUnit proof that pytest ran, identical-shape infra
   retry, serial authoritative test retry, source fingerprinting, coverage evidence,
   one-test-root enforcement, and serial CI parity remain green.
10. Repeated final canonical whole-suite runs pass, including the two formerly raced
    units; bounded failure evidence from the controlled pre-fix run is retained in
    this run's immutable F5c ledger.

## Affected Boundaries

| Producer | Format | Consumer | Probe |
|---|---|---|---|
| F0 scheduler/config | integer CPU weight + per-unit xdist policy | host lease and in-process budget | four-run fleet replay plus real concurrent lease acquisition |
| unit process supervisor | child tree lifecycle + bounded byte tail | retry classifier and report/evidence writer | timeout/cancellation subprocess with live grandchild |
| diagnostic evidence writer | bounded UTF-8 JSON under `.shipwright/runs/<run-id>/` | operator and race triage link | producer→disk→reader round trip, collision/path/control-character probes |
| progress reporter | ASCII line records | terminal/tool channel | closed stream, non-ASCII id, lifecycle ordering, maximum-length assertions |

## Verification (medium+)

- **Surface:** CLI
- **Runner:** canonical `uv run shared/scripts/tools/run_test_suite.py --project-root .
  --run-id iterate-2026-08-04-f0-fleet-throughput`, repeated on the final tree
- **Evidence path:** immutable run-specific F5c test-results entry plus run-scoped
  fleet and failure-diagnostic artifacts
- **F0.5:** the host-resource CLI probe must exit zero. Cancellation/timeout
  descendant cleanup and immediate lease/coverage reuse are assigned to the
  canonical shared-tools test root, whose native and integrated probes exercise
  those boundaries without overstating the narrower surface-verification artifact.

## Confidence Calibration

- **Boundaries touched:** suite config, host-weight admission, nested test fan-out,
  subprocess trees, temp files, coverage locks, JSON diagnostics, console progress.
- **Required empirical probes:** repeated whole-suite reproduction, integration alone
  with xdist on and off, tools alone, synchronized sibling lease overlap/FIFO, native
  Windows descendant cleanup, cancellation followed by immediate rerun, and canonical
  F0 on the final tree.
- **Anti-pattern check:** a clean run alone is not proof; fixed sleeps do not prove
  ordering; mocks do not prove Windows descendant cleanup; single-run latency does not
  select the fleet budget.

## External Plan Review Disposition

| Finding | Disposition |
|---|---|
| Windows tree cleanup was underspecified | Accepted: handshake launcher plus kill-on-close Job Object before uv can spawn; POSIX process group. |
| Per-unit weights could exceed the run budget | Inapplicable: no per-unit weight is added; xdist workers are already clamped to the grant. |
| Diagnostic JSON can persist secrets/untrusted text | Accepted: credential redaction, `untrusted` marker, safe paths, atomic publication, strict caps. |
| Fixed host value may fail elsewhere | Accepted in scope: `max_workers` is an upper request and P1.12 clamps it to detected capacity; evidence records both. |
| Integration policy was vague | Accepted: remove this root from xdist and pin the actual argv has no xdist flag. |
| Bounded output could alter classification | Accepted: classification remains rc plus JUnit existence; output consumers only render/store diagnostics. |
| Executor cancellation ordering was vague | Accepted: signal shared event, stop admission, reap trees, cancel queued futures, then shut down. |
| Cleanup might affect siblings | Accepted: remove only attempt-owned state; handle locks release themselves and sibling state is never deleted. |
| Budget selection was subjective | Accepted: candidate set, fleet size, repetitions, metrics, and tie rule are predeclared. |
| Progress could interleave/flood | Accepted: one locked emitter, cap after escaping, per-unit ordering, throttled heartbeats. |

## External Code Review Disposition

| Finding | Disposition |
|---|---|
| Live attempt output could grow without bound before the tail was read | Accepted: a dedicated reader now drains the pipe continuously into a fixed-size byte tail, and only that bounded tail is published to the attempt file. |
| The Windows probe did not exercise the complete uv/pytest/xdist/descendant tree | Accepted: the native probe now launches uv, pytest with two xdist workers, and an exited intermediate parent with a live grandchild, then verifies cancellation cleanup and immediate uv reuse. |
| Retry lifecycle did not distinguish the two retry authorities | Accepted: lifecycle records name `authoritative-serial` and `identical-shape-infra` explicitly. |
| Identical run/unit/phase evidence writes could overwrite a previous event | Accepted: every atomic evidence filename includes a UUID while preserving safe hashed path components. |
| Required review and immutable F5c evidence were not yet present | Expected sequencing: both are mandatory completion gates and are produced only after the final tested diff. |
| `suite_report.clean` was reported as undefined | Rebutted: `clean` is defined in the same module and its output remains covered by the report tests. |

## Stage-1 Spec Review Disposition

| Finding | Disposition |
|---|---|
| Fleet replay retained only three dominant durations per run | Accepted and fixed: three new uniquely named canonical audits retain all 18 unit durations each; the candidate replay was recomputed from those 54 measurements. |
| Cancellation probes did not traverse the real coverage/CPU lock stack | Accepted and fixed: an integrated `main()` probe now cancels inside the real coverage lock and repository-scoped CPU lease, observes both unwind, immediately invokes the runner again, and proves stale coverage state is reset. |

## Internal Code Review Disposition

| Finding | Disposition |
|---|---|
| The rendering truncation marker consumed bytes from the retained terminal tail | Accepted and fixed: evidence strips the presentation-only marker into a separate boolean and byte-caps from the end after redaction; regressions assert the terminal failure message survives. |
| A child could print the marker text and forge the inferred truncation state | Accepted and fixed: ProcessResult.truncated now travels as structured state through the executor, UnitResult, retry evidence, and rendering. Evidence never parses or removes child output; a regression pins the marker text as ordinary untrusted bytes. |

## Doubt Review Disposition

| Finding | Disposition |
|---|---|
| Natural child exit 130 was mistaken for parent cancellation | Accepted and fixed: an explicit cancellation boolean now controls interruption; natural 130 remains red infrastructure, while actual cancellation retains evidence and interrupts. |
| A cancelled retry emitted start but no completion record | Accepted and fixed: it now emits a bounded complete record with outcome cancelled and the retry authority before propagating interruption. |
| Race-card evidence linkage lacked a producer-to-store assertion | Accepted and fixed: the tracked item must retain evidencePath while captured output remains absent. |
| Diagnostic metadata bypassed credential redaction | Accepted and fixed: run, unit, phase, and tail are all redacted before JSON publication. |
| Worktree-local ignored evidence vanished at F11 cleanup | Accepted and fixed: evidence resolves through the canonical main repository into its ignored run store; a real linked-worktree test proves lifetime and placement. |
| The durable-root resolver broke the isolated runner import topology | Accepted and fixed: the resolver uses a package-relative leaf import and the standalone fixture carries both dependencies; the exact CLI E2E passes. |
| F0.5 evidence was credited with cleanup probes it did not run | Accepted and fixed in the Verification section: F0.5 proves the host CLI; native cleanup and immediate reuse belong to canonical tools-root evidence. |
