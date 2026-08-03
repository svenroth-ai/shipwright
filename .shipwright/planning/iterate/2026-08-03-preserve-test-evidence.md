# Iterate: preserve complete test evidence per run

- **Run ID:** `iterate-2026-08-03-preserve-test-evidence`
- **Type:** CHANGE
- **Complexity:** medium
- **Risk flags:** `touches_io_boundary`, `cross_component`
- **Affected FRs:** FR-01.10, FR-01.11
- **Spec Impact:** NONE — this closes an evidence-retention defect in the existing compliance and iterate lifecycle without changing their promised behavior.
- **Status:** verified

## Problem

`shipwright_test_results.json` is intentionally excluded from iterate PRs, but F5c durably copies only three selected fields. When an iterate worktree is removed, the detailed unit, integration, E2E, smoke and pgTAP results; failure and skip reasons; design fidelity; degraded state; source state; and coverage provenance disappear. The run-written ledger preserves those bytes only inside the temporary worktree.

## Decision

F5c must validate that the root test-results file is valid JSON and that `iterate_latest.run_id` equals the run being finalized. In the same locked transaction as the existing F5c summary, it atomically writes the source bytes unchanged to `.shipwright/agent_docs/iterates/<run_id>.test-results.json`. A missing, malformed, or foreign snapshot aborts finalization. The mutable root snapshot remains excluded from commits.

The one-time backfill accepts a candidate only when its embedded run ID has an existing durable F5c summary with the same run ID. It searches the explicitly known commits and extant worktrees, never substitutes an inherited main snapshot, never invents detail, and records recovered and unavailable runs in a small manifest. It is executed procedurally in this run with existing Git and evidence-validation primitives; no reusable backfill CLI or scanner is shipped.

The two durable files cannot be replaced atomically as a pair. Under the existing F5c lock the evidence artifact is installed first, then the summary. A crash after the first rename leaves a harmless, attributable artifact-only state; a retry verifies identical bytes and completes the summary. A legacy summary-only state may be repaired only from a currently validated matching snapshot. A different-byte artifact collision always fails without changing either file.

Backfill worktree candidates additionally must be modified relative to that worktree's checked-out commit; a clean inherited root snapshot is ineligible even when its embedded run ID has a durable summary. The root snapshot is already tracked in every candidate worktree in scope, so Git cannot report it as untracked (`??`); an explicit `M` provenance token is the complete admissible dirty-state grammar for this repository. Git candidates are limited to explicitly named commit/path pairs. Source bytes are read once in binary mode, decoded strictly as UTF-8, parsed with duplicate-key rejection, and installed unchanged. Canonical run-ID validation and regular-file/non-symlink checks precede path construction. Existing repository secret gates remain mandatory because the requested artifact is tracked and deliberately unredacted.

Exact-byte shipment is decided by comparing the committed blob with the validated working artifact at F11. The managed `-text -diff` attribute prevents Git normalization in every adopted/self-healed project and real-Git tests pin that propagation. The byte comparison remains the authority: it fails an effective normalization mismatch, while the mere absence of an attribute is not itself evidence loss when committed and working bytes are already identical.

## Acceptance Criteria

- **AC-1:** Given a valid current-run `shipwright_test_results.json`, when F5c appends the run summary, then `<run_id>.test-results.json` is created atomically beside it and is byte-for-byte identical to the source file.
- **AC-2:** Given a missing, malformed, non-object, missing-`iterate_latest`, or mismatched-run source snapshot, when F5c runs, then it exits non-zero and neither the F5c summary nor immutable snapshot is newly written or overwritten.
- **AC-3:** Given an F5c retry for the same run, when the current source bytes are identical, then it is idempotent; when they differ, the write is refused so immutable evidence cannot be mutated.
- **AC-4:** Given F5c is invoked through `finalize_bundle.py`, when the snapshot precondition fails, then bundle finalization stops at F5c and does not run F5b.
- **AC-5:** Given F6 staging and the derived-snapshot gate, when a run finalizes, then `<run_id>.test-results.json` is staged with the run while root `shipwright_test_results.json` remains excluded.
- **AC-6:** Given a candidate historical snapshot, when its embedded run ID exactly matches an existing durable F5c summary, then the backfill may write it under that immutable run name; otherwise it is rejected.
- **AC-7:** Given known P1 history and live sibling worktrees, when the one-time backfill runs, then every recoverable matching snapshot is committed, inherited stale main snapshots are not imported, and the manifest names both recovered and unavailable runs without invented detail.
- **AC-8:** Existing `<run_id>.json` summaries and the event projection remain unchanged and readable; consumer migration and the project coverage baseline remain out of scope.
- **AC-9:** Crash-recovery states are deterministic: artifact-only + same bytes repairs the summary; legacy summary-only + validated current bytes repairs the artifact; both-present + same bytes is idempotent; any different-byte collision fails without mutation.
- **AC-10:** Candidate validation rejects invalid UTF-8, duplicate JSON keys, symlinks, noncanonical/path-traversing run IDs, and worktree files cleanly inherited from their checked-out commit.

## Affected Boundaries

| Producer | Format | Consumer | Probe |
|---|---|---|---|
| F5 writes root test results | `shipwright_test_results.json` JSON bytes | F5c immutable-evidence writer | byte equality + run-id attribution tests |
| F5c CLI | summary JSON + `.test-results.json` | F6 staging, F11 verifier, future consumers | happy/error/idempotency integration tests |
| One-time operator procedure | explicit Git blobs and dirty worktree files | immutable evidence installer | matching-summary allowlist + stale-candidate rejection |
| `finalize_bundle.py` | F5c subprocess outcome | F5b invocation | failure stops orchestration test |

## Verification

- **Surface:** CLI
- **Runner:** focused pytest roots plus full repository F0 suite
- **Evidence path:** `.shipwright/runs/iterate-2026-08-03-preserve-test-evidence/surface_verification.log`

## Confidence Calibration

- **Boundaries touched:** F5 root snapshot → F5c immutable artifact; F5c → F6/F11; Git/worktree candidates → backfill importer.
- **Empirical probes run:** focused evidence/F5c tests, an atomic concurrent-writer race, real Git commit/worktree/backfill provenance tests, strict `M`-only worktree-status parsing, CRLF/exact-byte Git tests, finalize-bundle integration, CLI surface verification, the repository F0 suite split after a host `KeyboardInterrupt`, test-hygiene scan, Ruff, anti-ratchet, and the CI-parity diff-coverage gate. The final gate measured 425 changed lines at 89% coverage against refreshed `origin/main`, with an unchanged source fingerprint.
- **Test Completeness Ledger:** all acceptance criteria have executed evidence:
  - AC-1/AC-3/AC-9/AC-10: `test_iterate_test_results_evidence.py` covers exact bytes, malformed and ambiguous JSON, canonical IDs, symlink/reparse paths, stable reads, idempotency, collisions, locking, and both repair states.
  - AC-2: `test_f5c_rejects_foreign_current_snapshot_before_writing_either_artifact` plus the parametrized invalid-evidence and missing-snapshot cases prove fail-closed no-write behavior.
  - AC-4: `test_f5c_failure_stops_before_f5b` and the real bundle integration suite prove orchestration ordering.
  - AC-5: `test_test_results_evidence_check.py`, `test_gitattributes_exact_bytes.py`, and `test_parallel_iterates_no_merge_conflict.py` prove tracked immutable sidecars, exact CRLF-safe bytes, and continued exclusion of the mutable root snapshot.
  - AC-6/AC-7: `test_test_results_backfill_check.py` covers exact commit and dirty-worktree sources, reachability, genuine root commits, unavailable parents, inherited snapshots, unchanged pre-existing summaries, and committed artifacts; the verifier also passed against all 15 recovered artifacts in this run.
  - AC-8: existing summary/event tests and the full F0 suite remain green without changing the compact summary schema or event projection.
- **Confidence-pattern check:** depth is provided by byte/path/race/failure-atomicity tests, breadth by all repository roots plus lint and local guards, and integration composition by real Git repositories, worktrees, F5c/F5b orchestration, F6/F11 checks, and the CLI surface probe. One pre-existing Windows-only PID liveness test was deliberately deselected because `os.kill(os.getpid(), 0)` terminates its own process on Windows; the other tests in that file passed and the exclusion is recorded in the run evidence.

## Out of Scope

- Migrating consumers away from the existing flat F5c summary.
- Separating the project-wide coverage baseline from per-run results.
- Reconstructing or fabricating unavailable historical detail.
