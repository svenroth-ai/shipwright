# Mini-Plan: windows-ci-perf

- **Run ID:** iterate-2026-08-07-windows-ci-perf

## Files to create/modify

- `shared/scripts/lib/_windows_acl_trust.py` — new. Platform-independent
  (`ctypes`-free) home for `_TRUSTED_SYSTEM_SIDS`, `_TRUSTED_OWNER_SIDS`,
  and `_owner_is_trusted()`. Split out of `_windows_acl.py` in response to
  Stage 1 review (see spec's "Plan Review — findings applied"): that module
  imports `ctypes.wintypes` at module level, which cannot import on Linux,
  so the pure-logic regression tests below could not run in the required
  `ci.yml` gate without this split.
- `shared/scripts/lib/_windows_acl.py` — edit. Import `_owner_is_trusted()`
  from the new module and use it in `path_acl_is_private()`'s owner check
  (root-cause fix for trg-eed74a42); add `owner_sid_of()`.
- `shared/scripts/tools/tests/test_host_resource_locking.py` — edit. Add
  the `takeown /A` reproduction test (positive) and the two pure-function
  tests (negative + positive symmetry), importing `_windows_acl_trust`
  directly.
- `shared/scripts/tools/tests/test_windows_acl.py` — new. All seven ACL-
  specific tests (world-writable-ACL rejection, ACE-type support,
  Administrators-owned acceptance, spoofed-owner rejection, the two pure
  owner-trust tests, the wiring-pin test) moved here from
  `test_host_resource_locking.py`, which crossed the 300-line bloat gate
  once those tests accumulated — same split boundary as
  `_windows_acl.py`/`_windows_acl_trust.py` on the source side.
- `shared/scripts/tools/tests/test_f0_cli_diff_coverage_e2e.py` — edit. Add
  `_windows_acl_trust.py` to the `_RUNNER_FILES` manifest so the synthetic-
  repo E2E test can still import it (`trg-dc013d82` blind spot).
- `.github/workflows/windows-tests.yml` — edit. Single provisioning, `-n 4`
  on `shared/tests`, drop both `--deselect` flags now that their shared
  root cause is fixed.
- `.shipwright/planning/iterate/iterate-2026-08-07-windows-ci-perf/ci_supplychain_ack.json`
  — new, via `record_ci_supplychain_ack.py`.

## Work breakdown

1. **Root-cause investigation (done, this run):** traced both deselected
   tests to one shared call path (`f0_cpu_lease` → `host_resource_lease` →
   `_safe_runtime_root` → `path_acl_is_private`), confirmed via the actual
   error message and the fact both tests pass locally (non-admin-owned
   `LOCALAPPDATA`) but the triage card's own quoted CI failure message
   names the exact code path.
2. **Failing test first (Iron Law):** add
   `test_windows_private_root_accepts_administrators_owned_directory`
   (real `takeown /A` reproduction) to
   `test_host_resource_locking.py`, confirm it fails against the
   unmodified `_windows_acl.py`. Test expectation: `AssertionError` on the
   literal "not owned by the current user" message.
3. **Fix:** extract `_owner_is_trusted(owner_sid, current_sid)` into a new
   ctypes-free sibling module, `_windows_acl_trust.py` (split out mid-run
   per Stage 1 review, so the pure-logic tests below can run in the
   required Linux gate — see spec's "Plan Review — findings applied"), have
   `_windows_acl.py` import it and use it in the owner check, add the two
   pure tests (`test_windows_private_root_still_rejects_a_genuinely_foreign_owner`,
   `test_windows_acl_owner_check_accepts_a_trusted_system_principal`). Test
   expectation: all three new tests pass (the `takeown /A` positive one for
   real where privilege allows, gracefully skipping otherwise; the two pure
   ones always, no privilege needed); full `shared/scripts/tools/tests` at
   533 passed/0 new failures; both previously-deselected tests pass with no
   `--deselect`.
4. **Workflow restructure:** single `uv run --with ...` provisioning
   wrapping all three directories via `bash -c`, `-n 4` for `shared/tests`
   only, drop both `--deselect` flags, update the step's comment block to
   describe the new shape and cite the root cause. Test expectation: local
   run of the exact restructured command reproduces expected pass/skip
   counts for all three directories with no explicit deselects, xdist
   workers visibly engaged (`gw0..gw3`) for `shared/tests`.
5. **CI supply-chain ack:** `record_ci_supplychain_ack.py`
   `--consistent-with iterate-2026-06-01-ci-launch-hardening` (same
   posture precedent the original `windows-ci-tests` iterate cited: no new
   action introduced, no pin changed).

## Test strategy

- `_windows_acl.py` / `_windows_acl_trust.py`: new unit tests (one real
  OS-level reproduction via `takeown /A`, gracefully skipping without admin
  privilege; two pure tests — negative and its positive symmetry — needing
  no privilege) plus the full existing `test_host_resource_locking.py` +
  `shared/scripts/tools/tests` suite run for regression.
- `windows-tests.yml`: no unit tests exist for CI YAML — verification is a
  local native-Windows run of the exact restructured shell invocation, plus
  the live PR's own Actions run observed post-push.
- E2E: N/A (`surface: none`).

## Alternative approach (medium only)

**Alternative, for the perf half: route the whole job through
`run_test_suite.py`** instead of a raw pytest loop. **Rejected** — that
orchestrator folds in `--cov` measurement, diff-coverage gating, and
F0-specific retry/host-lease machinery this job explicitly does not want
(the original iterate's own comment already states "no diff-coverage GATE
applies to this job"). A raw pytest loop that reads the same worker
*inclusion* decision by hand, with a comment explaining the reduced worker
count, is the smaller change.

**Alternative, for the perf half: drop or path-filter the `push: branches:
[main]` trigger**, which buys a post-merge run with (per the workflow's own
comment) no automated consumer — cutting Actions-minutes roughly in half
with no engineering risk, and a strictly larger lever than either change in
scope. **Rejected for this iterate, not on the merits** — the operator's
scope for this run was explicitly the two performance causes named in the
Goal (parallelism, provisioning) plus the bugfix surfaced mid-flight; a
trigger change is a different kind of decision (what CI *observes*, not how
fast it runs what it already observes) and deserves its own iterate where
it's the whole ask, not a rider on this one. Flagged as a follow-up, not
taken on here — same treatment the original `windows-ci-tests` iterate gave
its own out-of-scope items.

**Alternative, for the bugfix half: relax `_windows_acl.py` by removing the
owner check for Windows entirely, keeping only the dangerous-ACE scan.**
**Rejected** — the owner check is what prevents a sibling low-privilege
account on a shared host from placing a lock file our process would follow
before we ever inspect its ACEs; removing it outright is exactly the
"weaken a security-hardening check" move the triage card explicitly warns
against. Extending trust to the SIDs the ACE check already trusts is a
narrower, already-precedented widening, not a removal.
