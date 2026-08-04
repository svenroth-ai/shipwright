# F0 Host Resource Lease

- **Run ID:** `iterate-2026-08-03-f0-host-resource-lease`
- **Status:** draft
- **Intent:** change
- **Complexity:** medium
- **Spec impact:** NONE — this changes internal F0 scheduling and evidence protection, not a product requirement.

## Problem

Each worktree currently derives its own F0 CPU budget and owns only a per-worktree
coverage lock. Sibling worktrees can therefore request the host budget independently,
oversubscribing the machine and racing while warming the shared uv cache.
The canonical runner also stays silent while long units execute because their output is
captured until completion; Codex Desktop has lost that long-lived output channel during
P1.10 even when the underlying test process completed.

## Scope

Introduce a reusable repository-keyed, cross-process and cross-worktree weighted host
resource lease. Enrol only F0: its CPU pool uses a host-wide weighted lease and its uv
warm-up uses a repository-wide exclusive lease. Preserve the existing per-worktree
coverage lock, suite retry rules, diff-coverage gate, exit codes, and CI verdicts.
Emit periodic progress while the suite is executing. Document optional, exhaustive
test-file shards as diagnosis only after an interrupted run; they never replace the
required successful canonical rerun.

Out of scope: browsers, scanners, builds, reviews, Stop hooks, CI parallelism, and any
consumer other than F0. A durable F0 completion receipt and automatic suite sharding are
deferred; receipt work is evidence-gated by a post-P1.12 terminal/toolcall comparison.

## Acceptance Criteria

1. Across sibling worktrees of one repository, the sum of live granted F0 CPU weights
   never exceeds `max(1, cpu_count - 2)`; an explicit per-run `suite.max_workers` is
   capped by that hardware budget.
2. Two F0 requests run concurrently when their combined weights fit the hardware budget.
3. When capacity is exhausted, requests wait in strict ticket order instead of failing;
   a smaller later request cannot bypass the queue head.
4. A waiting request prints the blocking queue owner and run id, then emits a periodic
   heartbeat until granted.
5. Killing a lease holder releases its capacity through the operating-system lock; the
   next waiter proceeds without deleting a stale lock file or trusting a PID timeout.
6. Sibling-worktree uv warm-ups are serialized while the independently granted F0 runs
   remain concurrent outside the warm-up critical section.
7. Repository identity maps sibling worktrees to one lease namespace and keeps unrelated
   repositories isolated.
8. The existing per-worktree `.coverage.f0.lock`, unit retry semantics, race triage,
   source fingerprinting, diff coverage, and exit-code precedence remain unchanged.
9. Tests exercise weighted concurrency, FIFO fairness, crash release, sibling worktrees,
   real Windows byte-range locking, and rejection of a writable-by-others Windows root.
10. F0 documentation describes host-wide sharing, queue output, crash recovery, the uv
    warm-up lease, and the retained per-worktree coverage lock.
11. While test units execute, the canonical runner emits an ASCII-safe periodic progress
    heartbeat containing the run id and completed/total unit count without changing or
    duplicating captured test output.
12. F0 guidance permits exhaustive, disjoint file shards only to diagnose an interrupted
    unit. Shard results are not an F0 verdict; the complete canonical runner must pass
    before F1.

## Affected Boundaries

| Producer | Format | Consumer | Probe |
|---|---|---|---|
| `host_resource_lease` state writer | internal UTF-8 JSON snapshot under the host temp lease namespace | sibling F0 lease contenders | producer→disk→consumer round-trip plus malformed/stale-owner recovery |
| OS owner-lock holder | locked byte in a per-ticket file | stale-entry reaper | live owner cannot be reclaimed; terminated owner is reclaimed without file deletion |
| F0 CPU lease | granted integer weight | `_Budget` outer/xdist scheduler | granted weight is the only in-process budget |

The JSON is machine-only. Operator-input probes for shell exports, inline comments,
quoted hashes, and empty env values do not apply; UTF-8, atomic replacement, malformed
state, and cross-process round-trip behavior do.

## Verification (medium+)

- **Surface:** CLI
- **Runner:** targeted pytest roots during TDD, then the canonical
  `shared/scripts/tools/run_test_suite.py` F0 command
- **Evidence path:** immutable run-specific F5c test-results artifact
- **F0.5:** execute `uv run shared/scripts/tools/suite_host_resources.py --probe
  --project-root . --run-id iterate-2026-08-03-f0-host-resource-lease`; it acquires and
  releases the F0 uv/CPU leases and must report a successful zero exit status. No web
  surface is affected.

## Confidence Calibration

- **Boundaries touched:** repository identity, host-temp JSON state, OS byte-range locks,
  F0 CPU scheduling, uv warm-up serialization.
- **Empirical probes run:** real sibling worktrees exercised weighted overlap, strict
  FIFO, serialized uv warm-up, crash release, and queue heartbeats; native Windows
  byte locks and unsafe ACLs were probed; same-process thread admission, ticket-open
  races, broken output streams, CLI acquire/release, and the POSIX fork/permission
  paths have direct tests. The canonical 18-unit F0 and the F0.5 CLI probe passed.
- **Test Completeness Ledger:** acceptance-criterion evidence is captured from the
  targeted 85-test regression block, canonical F0, F0.5 surface record, and review
  cascade; the immutable run-specific ledger is written and validated in F5c.
- **Confidence-pattern check:** breadth, depth, boundary, and composition checks are
  satisfied by native OS probes plus real-process/worktree tests; no mock-only
  concurrency claim or duplicated production logic is used as evidence.

## Decisions

- Use strict FIFO admission under a short repository/resource mutex. Live owners hold a
  unique OS byte lock for their full wait/grant lifetime; stale state is ignored only
  after that lock is successfully probed, so crash recovery does not depend on PID age.
- Derive the namespace from the resolved Git common directory (not the remote URL or a
  worktree-local `.git` file), hash it, and place it under a private per-user runtime
  root. Separate clones stay isolated. Every directory component and every mutex, state,
  or ticket file below the trusted runtime root is checked for links/reparse points;
  POSIX ownership/mode and Windows owner/DACL are checked fail-closed. Malformed state
  is never treated as empty while ownership is uncertain.
- Validate the runtime anchor too. A POSIX fallback may use a shared temp root only when
  it has safe root/current-user ownership and sticky-bit rename protection; an arbitrary
  writable `TMPDIR` fails closed. Windows accepts only the current-user-owned runtime
  root with a DACL that grants no write/delete access to untrusted principals; all
  unparsed ACE types are rejected.
- Ticket IDs are permanently unique UUIDs. Under the resource mutex, the process acquires
  its owner lock before atomically publishing `queued`; admission moves only the strict
  queue head to `granted`; release removes the entry before dropping the owner lock.
  Crash reaping removes an entry only after its owner lock is provably acquirable.
- Released ticket files are removed only as best-effort hygiene. Correctness never
  depends on deleting a stale lock file, and a surviving historical file is never reused.
- Lock order is non-nested: acquire/release the exclusive uv lease around uv preflight
  and warm-up first; only then acquire the CPU lease for suite execution through the
  final coverage verdict. This prevents idle warm-up waiters from reserving host CPU
  capacity, prevents AB/BA deadlocks, and keeps every CPU-bearing F0 phase budgeted.
- Normalize every CPU request through one function to `1..hardware_budget`, including
  defaults and oversized `suite.max_workers`; invalid configured values retain the
  existing suite-config error.
- Keep `.coverage.f0.lock` per worktree because it protects coverage artifacts local to
  that worktree; the new CPU lease protects the shared host capacity.
- Keep execution progress in the canonical parent process. A heartbeat improves both the
  agent tool channel and integrated-terminal visibility without changing unit commands,
  retry classification, JUnit evidence, or exit precedence.
