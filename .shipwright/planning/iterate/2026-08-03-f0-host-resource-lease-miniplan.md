# Mini-Plan — F0 Host Resource Lease

**Run ID:** `iterate-2026-08-03-f0-host-resource-lease`

## Files to create or modify

- `shared/scripts/lib/host_resource_lease.py` — reusable weighted admission/state layer.
- `shared/scripts/lib/_host_resource_locking.py` — private native locking and safe-path
  primitives.
- `shared/scripts/lib/_windows_acl.py` — native owner/DACL validation for the Windows
  runtime namespace.
- `shared/scripts/tools/run_test_suite.py` — F0 CPU/uv integration and active progress
  heartbeat.
- `shared/scripts/tools/suite_budget.py` — in-process weighted budget plus observable
  ordered parallel collection.
- `shared/scripts/tools/suite_gate_runtime.py` — source-stability and diff-coverage
  orchestration split from the legacy runner to avoid a size ratchet.
- `shared/scripts/tools/suite_host_resources.py` — F0-only uv and CPU lease adapters plus
  the supported F0.5 acquire/release probe.
- `shared/scripts/tools/tests/test_host_resource_lease.py` — deterministic state,
  weighting, fairness, repository identity, and heartbeat tests.
- `shared/scripts/tools/tests/test_host_resource_locking.py` — native Windows/POSIX
  byte-lock, ACL, ownership, and permission proofs.
- `shared/scripts/tools/tests/test_host_resource_lease_process.py` — real subprocess,
  sibling-worktree, crash-release, and Windows-lock tests.
- `shared/scripts/tools/tests/test_run_test_suite_faults.py` — process/fault
  classification regressions.
- `shared/scripts/tools/tests/test_suite_host_resources.py` — focused host-adapter,
  lease-lifetime, runner wiring, budget-cap, heartbeat, and oversize-budget tests.
- Existing F0 CLI/coverage/race harness tests — consume the new canonical leased-entry
  boundary and copy its standalone dependencies.
- `plugins/shipwright-iterate/skills/iterate/references/F0.md` — normative F0 contract.
- `docs/hooks-and-pipeline.md` — F0 suite-runner reference.
- `shipwright_test_config.json` — clarify host-budget semantics if the existing comment
  would otherwise claim per-run-only protection.

## Work breakdown

1. Write red unit tests for repository identity, weighted cap, strict FIFO, queue owner
   output, heartbeat timing, and state round-trip/recovery.
2. Implement the reusable lease with a private per-user runtime root, hashed resolved
   Git-common-dir identity, resource-separated atomic JSON state, a short state mutex,
   permanently unique ticket IDs, per-ticket OS owner locks, and context-managed release.
   Malformed/unsafe state fails closed; released ticket-file deletion is best effort only.
3. Add real-process tests using two git worktrees; prove compatible requests overlap,
   FIFO order holds, and a killed holder releases capacity. Exercise native Windows
   byte-range lock behavior and unsafe-root ACL rejection on Windows rather than mocking
   the platform.
4. Integrate F0 with a non-nested lock order: acquire/release the exclusive uv lease
   around xdist provisioning + `warm_up`, then acquire the weighted CPU lease for the
   actual suite and coverage work. Normalize every request to the hardware budget and
   pass the granted weight into `_Budget`. Retain `coverage_run_lock` unchanged around
   the whole per-worktree F0 invocation.
5. Emit ASCII-safe parent-runner progress heartbeats during long-running units. Document
   optional exhaustive file sharding as diagnosis only after interruption; require a
   subsequent complete canonical rerun before F1.
6. Update F0 docs and run targeted tests, boundary probes, reviews, canonical F0, lint,
   and local merge guards.

## Test strategy

- Unit: pure state transitions and queue rendering with controlled clocks.
- Integration: subprocesses in sibling git worktrees using real OS locks.
- Windows: the existing `ubuntu-latest` + `windows-latest` CI matrix executes native
  byte-range, ACL-rejection, and forcibly-terminated-holder tests; no platform-mocked
  substitute counts. POSIX independently proves its one-byte record lock.
- Regression: existing runner, fault, coverage, race-triage, and CI-parity suites.
- Full: canonical F0 after P1.10 no longer runs F0.

## Alternative considered

SQLite was rejected. It would serialize state updates, but a crashed process leaves a
granted row that still needs PID-age or stale-row recovery. An OS-held owner lock makes
process death the recovery signal directly and works without deleting rendezvous files.
