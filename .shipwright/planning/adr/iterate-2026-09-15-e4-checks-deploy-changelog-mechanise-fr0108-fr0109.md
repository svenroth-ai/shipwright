# ADR — Mechanise FR-01.08/FR-01.09 prompt-only-mechanisable ledger lines

**Run:** `iterate-2026-09-15-e4-checks-deploy-changelog`
**Campaign:** `req3-06-enforcement-mono`, sub-iterate `e4`

## Context

`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
carries AC-evidence-ledger rows for FR-01.08 (`/shipwright-deploy`) and
FR-01.09 (`/shipwright-changelog`) marked `prompt-only (mechanisable)` — the
described behaviour had no deterministic oracle proving it actually happens
at runtime, only prose in a SKILL.md an agent could ignore. Per the campaign's
D7 decision, a fake/weak gate is strictly worse than an honest downgrade to
`judgement` with a documented reason — so each row required either a real
check or an explicit, cited downgrade.

## Decision

Built real deterministic checks and updated the ledger to `enforced` /
`enforced, tested` for every row where a real oracle was possible:

- **`rollback_audit.py` (new)** — lock-guarded (`file_lock`), append-only
  JSONL trail at `.shipwright/deploy/rollback-history.jsonl`. `rollback.py`'s
  `main()` now calls `rollback_audit.record()` after **every** invocation,
  including a pre-flight refusal (e.g. an unreadable `--profile`) that used
  to return before any audit call — FR-01.08 criterion 7 ("every invocation
  is recorded, whatever it decided").
- **`shared/scripts/tools/verifiers/deploy_checks.py`** (new checks) —
  `check_failed_liveness_recorded_as_failed`, `check_manual_rollback_proves_alive`,
  hardened `check_test_gate_passed` — reconcile `smoke_test.py --output`
  evidence (`smoke-test-result.json`) against `phase_history[deploy]` and
  `rollback-history.jsonl`, with **fail-closed** timestamp parsing on
  **both** sides of every comparison (a missing/unparseable timestamp on
  either side fails the check, never silently passes).
- **`aggregate_changelog.py --fail-if-empty`** — refuses tagging a version
  that was never released and has nothing pending, with an accurate refusal
  message (the prior message falsely claimed to have checked legacy
  `[Unreleased]` bullets when it only checked drop files).
- **`validate-deploy.py` `_test_gate`** — a present-but-malformed
  `shipwright_test_results.json` now reads as `failing-*`, not silently as
  `no-results`; non-dict root/unit/e2e/smoke values are coerced safely
  instead of crashing the gate.

Two rows were **downgraded with a documented reason** rather than given a
fake gate:

- Best-effort `smoke_test.py --output` write (a filesystem write failure
  there must never mask the smoke test's own exit code — there is no
  deterministic oracle for "the write always succeeds").
- No release/run-identity binding across the rollback / smoke / changelog
  artifacts (inventing a new release-ID convention this codebase has
  nowhere else would be disproportionate to this sub-iterate's scope).

Both are cited explicitly, with rationale, in the ledger rows themselves
(`2026-07-23-req3-ac-evidence-ledger-mono.md`, FR-01.08 rows #4 and #8).

## Consequences

- Two new durable write surfaces recorded in `architecture.md`:
  `.shipwright/deploy/rollback-history.jsonl` and
  `.shipwright/deploy/smoke-test-result.json`.
- `deploy_checks.py` is a new file crossing the 300-LOC bloat baseline
  (351 lines, new baseline entry); several touched test files were
  re-baselined upward for genuine test growth. `anti_ratchet_check.py
  --worktree` confirmed clean (no ratchet).
- `smoke_test.py`'s `main()` no longer persists a usage-error
  (`ProfileError`/`ValueError`) via `--output` — a config/operator mistake
  is no longer at risk of being reconciled as a real liveness failure.

## Rationale

Two rounds each of external plan review (GLM + OpenAI via openrouter) and
external code review found genuine fail-open bugs that hand-written fixture
tests alone had missed:

1. `check_manual_rollback_proves_alive` checked only timestamp presence/
   ordering, never `smoke.get("success")` — a rollback followed by a
   liveness check that found the app **still down** would still report
   "proves alive". Found via an ADR-024 real producer→consumer round-trip
   probe (not a hand fixture) during Self-Review, and fixed.
2. `check_failed_liveness_recorded_as_failed`'s round-1 fix only fail-closed
   when the `phase_history` side's timestamp was unparseable; round-2
   external code review caught the mirror-image fail-open bug — an
   unparseable `checked_at` (the smoke side) was skipping the check
   entirely. Fixed with an explicit early fail-closed branch.
3. A bad `--profile` or malformed `--url` was being persisted via
   `--output` into the same durable file the liveness-reconciliation check
   reads. Round-2 external code review flagged the risk of a config typo
   being reconciled as a real app-down failure; fixed by removing the
   `_write_output` call from `smoke_test.py`'s usage-error branch entirely.
4. **F0's own canonical suite runner** (`run_test_suite.py`, driving
   `integration-tests/test_devops_flow.py` against THIS repo's real
   `shipwright_test_results.json`) caught a bug none of the hand-written
   unit tests could, because they all seeded an isolated `tmp_path` fixture
   instead of reading the real file: `shipwright_test_results.json` has
   **two producers with two different shapes** — the full-pipeline
   `/shipwright-test` phase writes `unit`/`e2e`/`smoke` at the top level
   (the shape `_test_gate` and `check_test_gate_passed` were written to
   read, mirroring `phase_validators._validate_test`), while
   `/shipwright-iterate`'s F5 step nests the identical sub-keys under an
   `iterate_latest` wrapper. Reading only the top level made both new gates
   a **permanent no-op in every iterate-run repo** — including this very
   monorepo, which runs almost exclusively via `/shipwright-iterate`. Fixed
   by falling back to the `iterate_latest` block when the top level has no
   `unit` key. The same real-file probe also exposed a second, independent
   bug: `_test_gate` required `e2e.status in ("passed", "skipped")` as a
   hard block, which would refuse *every* deploy in a backend-only,
   e2e-less repo (`e2e.status` routinely reads `"not_run"` here) — fixed by
   making E2E non-blocking except on a reported `"partial"` (a real
   failure signal), matching `_validate_test`'s own established convention
   that E2E is an "inform"-only warning, never an "ask" gate (constitution:
   "E2E can be flaky"). Both fixes are covered by new regression tests
   reading the `iterate_latest`-nested shape and asserting `not_run`
   non-blocking / `partial` still-blocking, in both
   `plugins/shipwright-deploy/tests/test_validate_deploy.py` and
   `shared/tests/test_verifiers_test_changelog_deploy.py`.

Every accepted finding is recorded `accepted-and-fixed` (with the concrete
fix) in the iterate's `External-Plan-Review-Findings` /
`External-Code-Review-Findings` tables; every rejected finding is recorded
`rejected-with-reason` with the empirical evidence that disproved it.

## Rejected findings (with evidence)

- **GLM round 1, HIGH: "`rollback.py` crashes with `Path(None)` TypeError
  when `--project-root` is omitted."** Empirically disproven — ran the CLI
  directly without `--project-root`; no crash occurred, because the CLI's
  own argparse default is `"."`, never `None`. Rejected with the cited
  run. (The exercise did surface a real, separate doc gap — the SKILL.md's
  documented PROD/clone rollback invocation never passed `--project-root`
  at all, which was fixed.)
- **OpenAI, repeated across both rounds: "`aggregate()` regressed to
  accepting its parameters positionally."** Empirically disproven by
  reading the actual signature — a `*,` keyword-only marker already
  precedes every parameter in question, making the claimed regression
  impossible. Rejected both times with the signature cited.

## Self-caught slip (not an external-review finding)

Fixing the diff-coverage gate's missing lines required adding in-process
(not subprocess) coverage tests. Comparing the touched test file against
`origin/main` line-by-line during that work surfaced a separate, unrelated
regression from earlier in this same sub-iterate: an editing pass had
silently dropped the final assertion (`assert recording.calls`) from a
pre-existing AC15 test in `test_rollback.py`, caught only because `ruff`'s
F841 flagged the now-unused `recording` variable it used to close over.
Restored verbatim; `diff --strip-trailing-cr` against the merge-base
confirmed no other touched file lost content the same way. Separately,
F0's `test_fold_map_e2e.py` (the fold-map/traceability manifest gate) caught
a real authoring mistake in the two new diff-coverage regression tests: a
non-zero-padded `@pytest.mark.covers("FR-01.08/AC5")` — the canonical ID is
`AC05`, matching every other two-digit marker already in the file. Fixed.

## Rejected alternatives

- Building a "gate" that only checks the *presence* of a rollback-history
  entry or a smoke-test-result file (without reconciling timestamps or the
  `success` field against the actual event it claims to prove) — rejected
  as exactly the kind of fake/weak gate D7 forbids: it would pass even when
  the underlying claim ("the app is alive after this rollback") is false.
- Inventing a new release/run-identity convention to bind the rollback,
  smoke, and changelog artifacts together — rejected as disproportionate
  scope for this sub-iterate; documented as a residual limitation instead.
