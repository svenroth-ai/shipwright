# Spec / requirement — P2.41a: gate_policy read-leg parity

**Run ID:** iterate-2026-08-07-gate-policy-durable-read-parity
**Status:** implemented
**Complexity:** small (risk flags: `touches_io_boundary`; `touches_rls` also
fired but is a keyword false-positive — the diff does not touch RLS/migrations)

## Problem

`gate_policy.read_run_config_mode` reads `shipwright_run_config.json` with a
plain `Path.read_text`, while `orchestrator_pkg.config_io._read_parse_shape`
reads via `durable_read_text`, which retries for `READ_RETRY_BUDGET_SECONDS`
(2.0s) past the delete-pending `PermissionError` a concurrent `os.replace`
causes on Windows. The reporter therefore answers `INERT_MODE` on the very
first such transient error, while the orchestrator reads the config
successfully — so the two can disagree about whether a run is driven while
the config is being rewritten underneath them.

Content-class parity (decode / parse / shape / BOM) was already closed
(`iterate-2026-08-06-shared-read-run-config-mode-guard`). This is the
remaining READ-LEG asymmetry, numbered 2026-08-06 as P2.41a — a tail item of
P2.41 (PR #585). Direction is fail-safe (inert, never a weakened gate) and
the divergence requires a concurrent writer to observe, so severity is Low.

## Acceptance

- [x] `read_run_config_mode` retries a transient Windows delete-pending read the
  same way `config_io`'s strict reader does, instead of degrading to
  `INERT_MODE` on the first violation.
- [x] The two readers must not be observed to disagree under an identical
  simulated concurrent-rewrite race.
- [x] The existing fail-safe direction is preserved: a *genuinely* stuck holder
  (past the retry budget) still degrades to `INERT_MODE`, never crashes the
  caller.
- [x] `gate_policy.py` stays within its grandfathered bloat-baseline line count
  (301, zero headroom) — no baseline bump.
- [x] Content-class parity (already closed) must not regress.

## Confidence Calibration

- **Boundaries touched:** `touches_io_boundary` — `shipwright_run_config.json`,
  read concurrently with a writer's `os.replace` on Windows.
- **Empirical probes run:**
  - Simulated a Windows delete-pending sharing violation (`Path.read_text`
    raising `PermissionError` winerror 5) and confirmed the reporter now
    retries and resolves `SINGLE_SESSION` instead of degrading on the first
    violation.
  - Shortened the retry budget to 0.02s and confirmed a genuinely stuck
    holder still degrades to `INERT_MODE` — fail-safe direction unaffected.
  - Replayed an identical simulated race against both `config_io.read_run_config`
    and `gate_policy.read_run_config_mode` and asserted the same verdict
    (the direct cross-tree parity claim, not just isolated reporter behavior).
  - `git stash`-verified both new regression tests genuinely FAIL against the
    pre-fix `gate_policy.py` (not vacuously passing).
- **Test Completeness Ledger:**

  | Behavior | Status | Evidence |
  |---|---|---|
  | Reporter retries a transient Windows delete-pending read and resolves `SINGLE_SESSION` | tested | `shared/tests/test_gate_policy_read_retry.py::test_read_run_config_mode_survives_a_windows_delete_pending_read` |
  | Reporter still degrades to `INERT_MODE` past retry-budget exhaustion | tested | `shared/tests/test_gate_policy_read_retry.py::test_read_run_config_mode_still_fails_safe_past_the_retry_budget` |
  | The two readers agree under an identical simulated race | tested | `plugins/shipwright-run/tests/test_runconfig_read_retry_parity.py::test_the_two_readers_agree_under_the_identical_flaky_read` |
  | Content-class parity (decode/parse/shape/BOM) unaffected | tested | pre-existing `shared/tests/test_gate_policy.py` suite, re-run green |
  | `gate_policy.py` stays at its 301-line bloat-baseline cap | tested | `wc -l` + `ruff check`, re-verified after every edit |
  | Non-Windows platforms unaffected (single-attempt read, no behavior change) | untestable | reason_code: platform-gated — `_is_windows()` short-circuits to a no-op off Windows, so the retry path is only reachable via the patched simulation already covering it; a real non-Windows run exercises no new code path to test |

  0 untested-testable.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the `git stash` regression check was repeated after
    every edit that touched `gate_policy.py`, confirming the fix stayed
    necessary and sufficient rather than accidentally passing; the parity
    test's own stale-closure construction bug was itself caught by adversarial
    doubt review (D-5) and independently re-verified fail/pass afterward.
  - *Coverage (breadth):* the isolated reporter behavior, the cross-tree
    parity claim, and the pre-existing content-parity suite are each tested
    independently, so a regression in any one layer is caught without relying
    on the others to mask it.
