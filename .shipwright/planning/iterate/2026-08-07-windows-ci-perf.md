# Iterate Spec: windows-ci-perf

- **Run ID:** iterate-2026-08-07-windows-ci-perf
- **Type:** change (bundles a root-caused bug fix; see Root Cause below)
- **Complexity:** medium
- **Status:** implemented

## Goal

`.github/workflows/windows-tests.yml` (landed 2026-08-05 via #571, IT-9 Unit
5) runs the three `shared/` test directories on `windows-latest`: once on
`pull_request` and once more on `push` to `main` post-merge (not twice per
PR — `push` is filtered to `branches: [main]`). Measured 2026-08-07: 24m39s
and 27m45s, on a 2x-billing-multiplier runner. It is not a required check, so this is
Actions-minutes and signal-latency cost, not a correctness gap by itself —
but mid-flight, the operator surfaced open triage item **trg-eed74a42**
("P3.05a [AUTO after PR #571] Two Windows-only F0 defects the first Windows
CI job exposed"), which bundles two tests the job deselects
(`trg-e82d8771`, `trg-d0f585b2`). Root-causing that bundle (below) found
both share one cause in security-sensitive shared code, so it is folded
into this run rather than filed separately — the same 2x-billed Windows
round-trip needed to prove the perf change would otherwise be spent again
proving the bugfix alone. Three independent causes are addressed:

1. The job runs plain pytest with no parallelism, while
   `shipwright_test_config.json`'s `suite.xdist` allowlist already records
   `shared/tests: 8` as measured-safe for fan-out. The windows job invokes
   pytest directly (not through `run_test_suite.py`), so nothing currently
   reads that allowlist for it. **This is the dominant lever, confirmed by
   live per-directory timing**: on the two most recent live runs (GH Actions
   run IDs 31181135569, 31180329620), `shared/tests` alone took 21m49s and
   24m29s respectively — 88-93% of the whole step's wall clock.
   `shared/scripts/tests` (13s) and `shared/scripts/tools/tests` (~64s) are,
   by comparison, noise.
2. The job provisions the ephemeral pytest environment three times via
   separate `uv run --with ...` invocations, once per directory, when the
   packages needed are identical across all three. **This is the smaller
   lever**: the same live logs show near-zero visible provisioning gap
   between directories on the actual runner (`astral-sh/setup-uv`'s
   `enable-cache: true` is already warm), so collapsing to one provisioning
   call is expected to save tens of seconds, not minutes — worth doing
   because it is free and simplifies the step, not because it moves the
   headline number.
3. Two tests are permanently deselected from this job
   (`shared/scripts/tools/tests/test_run_test_suite_faults.py::test_main_cancellation_releases_real_locks_and_next_run_resets_state`,
   `shared/scripts/tools/tests/test_f0_cli_diff_coverage_e2e.py::test_the_f0_cli_stops_on_an_under_covered_diff_then_passes_once_covered`)
   because of a genuine defect in `shared/scripts/lib/_windows_acl.py`'s
   ownership check — root-caused below, not previously understood as one
   shared cause.

## Root Cause (trg-eed74a42 — Iron Law investigation)

**Symptom, as triaged:** two tests fail on `windows-latest` but pass on
`ci.yml`'s Linux job. The triage card's own working theory treated these as
two *separate* defects needing two separate root-causers — a Windows
Job-Object cancellation exit-code mismatch for test (1), and an unexamined
ACL rejection for test (2).

**Investigation (this run):** both tests exercise
`shared/scripts/lib/host_resource_lease.py`'s `host_resource_lease()`,
whose *first* action (`_safe_runtime_root`, before any ticket/mutex work)
validates that `LOCALAPPDATA` (`_private_location()`'s anchor on Windows) is
"private" via `shared/scripts/lib/_windows_acl.py::path_acl_is_private()`.
That function's owner check required an *exact* SID match between the
directory's recorded owner and the current process token's user SID:

```python
if _sid_string(owner, advapi, kernel) != current:
    return False, "directory is not owned by the current user"
```

— the literal message quoted in the triage card for test (2). GitHub-hosted
`windows-latest` runs as `runneradmin`, and provisions that account's
`AppData\Local` tree with an owner of `BUILTIN\Administrators`
(`S-1-5-32-544`) rather than `runneradmin`'s own user SID — a normal
consequence of an admin-provisioning image build, and *already* a trusted
principal for this same function's ACE-danger check three lines further
down (`_TRUSTED_SYSTEM_SIDS`), just not for the owner check above it.

For test (1), `f0_cpu_lease()` (real, only lifecycle-tracked, not mocked in
the test) goes through the identical `host_resource_lease()` call **before**
the mocked `run_suite()` that is supposed to raise the test's synthetic
`KeyboardInterrupt` is ever reached. On the real runner, the ownership
check above fails first, raising `HostLeaseError` — which
`run_test_suite.py::main()`'s `except (SuiteConfigError, HostLeaseError):
return 2` catches, producing exactly the observed "returns 2" symptom
without the cancellation path (Job Object, exit-code convention) ever being
exercised. **The two triaged "defects" are one defect**, surfacing through
two different assertions because of where each test happens to look.

**Fix:** `_windows_acl.py::path_acl_is_private()`'s owner check now accepts
an owner that is either the current user's own SID *or* a member of
`_TRUSTED_OWNER_SIDS` (extracted, along with the narrower-vs-`_TRUSTED_SYSTEM_SIDS`
rationale below, to a new, independently-unit-testable `_owner_is_trusted()`
in a new ctypes-free sibling module, `_windows_acl_trust.py` — see "Plan
Review — findings applied" for why owner-trust and why the module split).
This is not a weakening of the security property,
for two independent reasons found during internal plan review, not just
the first-principles argument this section originally made:

- **POSIX-parity precedent, in the same function's sibling branch.**
  `_host_resource_locking.py::_safe_runtime_root()`'s POSIX branch already
  does exactly this: `if info.st_uid not in {0, current_uid}` accepts root
  (uid 0) as a legitimate owner alongside the current user. The Windows
  branch was stricter than the POSIX branch it mirrors; this fix brings the
  two to parity rather than introducing new trust.
- **Owner assignment requires privilege the threat model excludes.**
  *(Corrected by Stage 3 doubt review — see "Doubt Review — findings
  applied" below; the original bullet here argued "zero marginal
  capability" via the ACE-danger loop, which Stage 2 already found
  factually wrong: the owner check runs BEFORE that loop and is exactly
  what rejected these SIDs pre-fix, so nothing was "already accepted".)*
  Absent `SeRestorePrivilege`, a process can only set an object's owner to
  a SID already present in its own token — a non-administrator on a shared
  host cannot forge `BUILTIN\Administrators` or `LocalSystem` ownership on
  a directory it creates, so the widened branch is unreachable by the
  low-privilege-sibling-account threat this check exists to stop. An
  adversary who *can* reach it is already a local administrator, who
  defeats this whole check via `SeTakeOwnershipPrivilege` regardless of
  what `_owner_is_trusted()` decides.

Verified (see Test Completeness Ledger): a real `takeown /A`-owned
directory is now accepted where privilege allows reproducing it (and
hard-fails, not silently skips, when that reproduction is expected to work
— i.e. under `CI`), a pure negative-case test pins that a genuinely foreign
owner SID is still rejected, a symmetric pure positive-case test pins that
a trusted system SID is accepted, and both previously-deselected tests now
pass locally with no `--deselect` applied.

**Falsifier.** The claim that both deselected tests share this one cause is
directly observed for test (2) (`test_the_f0_cli_stops_on_an_under_covered_diff_then_passes_once_covered`
fails with the literal owner-check message) and, on closer inspection
(Stage 3 doubt review), is actually *deductively settled* rather than
merely inferred for test (1) too. The triage card's original alternative
theory — a Windows Job-Object cancellation exit-code mismatch — cannot
apply to this specific test at all:
`test_main_cancellation_releases_real_locks_and_next_run_resets_state`
calls `mod.main()` **in-process** (no subprocess, no OS signal) and its
mocked `run_suite()` raises a **synthetic** `python`-level
`KeyboardInterrupt`, so no Job Object or exit-code-from-signal conversion
is ever on this call path; `main()`'s own `except KeyboardInterrupt: return
_RC_CANCELLED` (`_RC_CANCELLED = 130`, a plain module constant in
`suite_process.py`) is the ONLY route to a 130, and the observed pre-fix
result was 2, matching only `except (SuiteConfigError, HostLeaseError):
return 2` — which requires the lease check to have failed and short-
circuited before the mocked `run_suite()` is ever reached. **If, after
this fix, the live PR's Windows Actions run shows test (2) green and test
(1) still red, the single-cause theory is refuted, but NOT in favor of the
Job-Object theory this section originally pointed back to** — that
alternative is ruled out by the code shape above, not merely superseded.
A red test (1) post-fix instead means either the ACL fix is insufficient
(see the ACE-danger-loop caveat two paragraphs below — the loop has never
been exercised against the runner's actual inherited ACEs) or a third,
not-yet-identified cause; re-`--deselect` test (1) alone with the new
runner output and open a fresh triage item to investigate which, rather
than reopening `trg-e82d8771` under its original theory. Keep the
`_windows_acl.py` fix regardless — it
is independently justified by test (2) and the arguments above regardless
of test (1)'s outcome.

**ACE-danger-loop caveat (Stage 3 doubt review).** `path_acl_is_private()`
has two independent branches: the owner check (fixed and tested here) and
the pre-existing ACE-danger loop, which rejects any dangerous ACE granted
to a principal outside `_TRUSTED_SYSTEM_SIDS | {current}`, or any ACE of an
unsupported type (`_ace_type_is_supported` only accepts types 0/1 —
conditional/callback ACE types are rejected outright). Every regression
test this run adds isolates the owner branch specifically (the `takeown
/A` test resets the DACL to a synthetic minimal one *before* the ownership
assertion, precisely so an unrelated ACE issue can't misattribute a
failure to the owner check) — so nothing in this run's local evidence
says whether the real `LOCALAPPDATA` tree on `windows-latest` also clears
the ACE loop. `windows-tests.yml`'s restructured step now prints that
verdict directly (see below) so the live run observes it rather than
assuming it; if it disagrees, that is the "ACL fix insufficient" branch of
the falsifier above, not evidence against the owner-check fix itself.

## Acceptance Criteria

- [x] (AC1) `shared/tests` runs under pytest-xdist on the Windows job, sized
  to `windows-latest`'s 4 cores (`-n 4`) — mirroring the
  `shipwright_test_config.json` `suite.xdist` allowlist's *inclusion* of
  `shared/tests`, not its Linux worker count.
- [x] (AC2) `shared/scripts/tests` and `shared/scripts/tools/tests` stay
  serial (unchanged) — neither is in the `suite.xdist` allowlist.
- [x] (AC3) The pytest environment is provisioned by exactly one
  `uv run --with ...` invocation for the whole job step, not once per
  directory.
- [x] (AC4) The job still fails closed: a test failure in any of the three
  directories still fails the step.
- [x] (AC5) `_windows_acl.py::path_acl_is_private()` accepts an owner SID
  that is a member of `_TRUSTED_OWNER_SIDS` (Administrators, LocalSystem —
  the narrower two-member subset of `_TRUSTED_SYSTEM_SIDS` that can
  realistically own a real filesystem object), in addition to an exact
  current-user match.
- [x] (AC6) `_windows_acl.py::path_acl_is_private()` still rejects a
  genuinely foreign (untrusted) owner SID — the fix does not widen trust
  beyond the already-trusted set.
- [x] (AC7) Both previously-deselected tests
  (`test_main_cancellation_releases_real_locks_and_next_run_resets_state`,
  `test_the_f0_cli_stops_on_an_under_covered_diff_then_passes_once_covered`)
  run (not deselected) in `windows-tests.yml` and pass locally with no
  `--deselect` applied.
- [x] (AC8) `ci.yml` and every other workflow file are untouched — this is
  scoped to `windows-tests.yml` plus `shared/scripts/lib/_windows_acl.py`
  (where the root cause lives), its new sibling `_windows_acl_trust.py`
  (split out per Stage 1 review — see "Plan Review — findings applied"),
  their test files (`test_host_resource_locking.py`, its new sibling
  `test_windows_acl.py` — split out post-Stage-3 when the ACL-specific
  tests pushed the original file over the 300-line bloat-gate limit, same
  boundary as the source-side split — plus the `_RUNNER_FILES` manifest
  entry in `test_f0_cli_diff_coverage_e2e.py` the source split required),
  plus the run-scoped governance artifacts finalization itself writes
  (`ci_supplychain_ack.json`, `reviews.json`, this
  spec/mini-plan/architecture-brief) — those are expected, not scope creep.

## Spec Impact

- **Classification:** none
- **NONE justification:** framework/CI-infrastructure change (workflow
  performance) plus an internal-tooling security-check bug fix; no
  target-app FR — this repo's own `spec.md` files describe Shipwright's
  product surface, not its own CI/test-runner plumbing. Same precedent as
  `iterate-2026-08-05-windows-ci-tests`.

## Out of Scope

- Making the job a required (branch-protection) check.
- Registering the new xdist worker count in `shipwright_test_config.json`'s
  `suite.xdist` — that config drives `run_test_suite.py` (Linux), which
  this job does not go through; an entry there would claim a measurement
  this iterate did not make.
- Applying xdist to `shared/scripts/tests` or `shared/scripts/tools/tests`
  — not in the allowlist, no measurement backs it.
- Any other `_windows_acl.py` hardening beyond the one owner-check gap the
  root cause identified (e.g. re-auditing the ACE-danger loop) — untouched,
  unrelated to trg-eed74a42.

## Design Notes

N/A — no UI surface.

## Affected Boundaries

n/a — no serialized producer/consumer format is introduced or changed.
(Stage-1 message classification flagged `touches_io_boundary` from the
phrase "`shipwright_test_config.json`" in the scoping description; the
diff-driven recompute — `is_io_boundary_change` over the changed files —
returns `False`. The flag does not survive contact with the actual diff.)

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-07-windows-ci-perf/architecture_brief.md`
- **Verdicts:** deepseek=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed — one `uv run`
  for provisioning, `-n 4` scoped to `shared/tests` only, the existing
  trusted-owner set (no new standing mechanism).
- **Findings:** none from either reviewer.
- **Reconciliation:** n/a — no objection to reconcile.

## Plan Review — findings applied

The internal Opus plan review (verdict: revise) and the external Branch A
review (openai: revise, deepseek: approve) converged on the same class of
issue: the *evidence* that the fix works was weaker than the fix itself.
Applied before build:

- **Positive proof test no longer skips silently in CI** — hardened to
  `raise AssertionError` (not `pytest.fail`, which CodeQL flags as an
  implicit return and blocks automerge) when `CI` is set and `takeown /A`
  cannot reproduce the scenario, instead of a green skip.
- **The anti-over-widening regression test runs in the required gate** —
  dropped its `skipif(win32)`; it is pure string comparison and now runs on
  `ci.yml` (required), not only the advisory Windows job. Added its
  positive counterpart for symmetry.
- **Narrowed the trusted-owner set.** Both external reviewers independently
  flagged that reusing the full `_TRUSTED_SYSTEM_SIDS` (which includes two
  ACE-only inheritance-placeholder SIDs, `S-1-3-0`/`S-1-3-4`, that can never
  be a real object's resolved owner) for the *owner* comparison was
  imprecise. Introduced `_TRUSTED_OWNER_SIDS = {LocalSystem,
  Administrators}` — the two members that can realistically own a real
  filesystem object — and use that instead.
- **Independent proof of the observed owner SID.** Extracted
  `owner_sid_of()` from `path_acl_is_private()` and asserted, in the
  `takeown /A` test, that the resulting owner is literally `S-1-5-32-544`
  before asserting the function accepts it — closes the "proves a directory
  *can* become Administrators-owned, not that this *is* the shape" gap.
- **Full caller audit recorded.** Grepped the whole repo for
  `path_acl_is_private`/`_windows_private`: the only caller is
  `_host_resource_locking.py` (used exclusively by `host_resource_lease.py`
  / the F0 host-resource lease). No other consumer exists.
- **Fail-closed propagation proven, not just asserted.** Ran the exact
  restructured `bash -c` wrapper with a deliberately-failing first
  directory (`pytest -k "matches_nothing"`, exit 5) — confirmed the
  script's own exit code is 5 and the loop's later directory is never
  reached, before relying on `set -euo pipefail` by inspection alone.
- **Root Cause section gained the POSIX-parity and zero-marginal-capability
  arguments**, and a stated falsifier for the single-cause theory (see Root
  Cause above) — both requested independently by the internal and external
  reviews.
- **Predicted a specific post-change wall-clock band** (10-14 min, down
  from 24-28) from live per-directory timing pulled off two recent CI run
  logs, so the performance AC is falsifiable rather than "it got faster."
- **Split `_owner_is_trusted`/`_TRUSTED_OWNER_SIDS`/`_TRUSTED_SYSTEM_SIDS`
  into a new module, `shared/scripts/lib/_windows_acl_trust.py`.** Caught by
  Stage 1 (`spec-reviewer`, CRITICAL, blocking): `_windows_acl.py` imports
  `ctypes.wintypes` at module level, which raises `ValueError` on import on
  Linux (the `'v'` VARIANT_BOOL field type is Windows-only) — so once the
  two pure-logic regression tests dropped their `skipif(win32)` guard (the
  bullet above) to run in the required `ci.yml` Linux gate, they could not
  `from scripts.lib import _windows_acl` without redding that gate. The new
  module carries only the two constants and `_owner_is_trusted()` (no
  ctypes import); `_windows_acl.py` imports from it, and the two pure tests
  import `_windows_acl_trust` directly instead. Also required adding the
  new file to `test_f0_cli_diff_coverage_e2e.py`'s `_RUNNER_FILES` manifest
  (the synthetic-repo E2E test's own list of `scripts/lib/*.py` files it
  copies — a known blind spot the manifest's own comment already documents
  from `trg-dc013d82`).

**Not applied — explicitly rejected, with reason:**
- OpenAI's suggestion to weaken owner-trust to require the current process
  token itself carry the trusted SID (a strictly narrower control, still
  covers `runneradmin`): rejected, but the reason recorded here at the time
  was itself the "zero marginal capability" argument Stage 2 later found
  factually wrong (see Root Cause) — Stage 3 doubt review caught that this
  section's rejection had gone stale along with it. The rejection now
  stands on the surviving argument instead (Root Cause, corrected bullet):
  a non-admin cannot forge the trusted owner SIDs at all (no
  `SeRestorePrivilege`), so the token-membership check would add a ctypes
  token-group enumeration for a security delta that is already closed by
  privilege, not by the ACE loop. The external review's own distinct
  security finding is the *narrower-set* concern (`_TRUSTED_OWNER_SIDS` vs
  `_TRUSTED_SYSTEM_SIDS`), which *was* applied and is unaffected by this
  correction.
- Dropping/path-filtering the `push: branches: [main]` trigger (raised by
  the internal review as a larger lever): explicitly out of scope for this
  run (see mini-plan Alternatives) — a different kind of decision than what
  the operator asked for, flagged as a follow-up.

## Code Review — findings applied

Stage 2 (`code-reviewer`, opus): verdict APPROVE WITH COMMENTS, no blocker.
One real gap and several worthwhile low-severity findings, applied before
Stage 3:

- **AC6 was proven only at the pure-helper boundary, not at
  `path_acl_is_private()` itself** (medium — a deleted owner check, exactly
  the "remove it entirely" move the mini-plan's alternatives reject, would
  leave every existing test green). Added
  `test_windows_private_root_rejects_a_spoofed_foreign_current_user`
  (win32-gated): monkeypatches `_current_sid` on a directory the test
  process genuinely owns, so the owner comparison itself fails, and asserts
  `path_acl_is_private()` returns `(False, ...)` with the expected message.
- **The security rationale in `_windows_acl_trust.py`'s docstring was
  factually wrong** — it claimed the widened owner SIDs were "already
  accepted... before this change" via the ACE-danger loop, but the owner
  check ran first and is exactly what rejected them; owner identity also
  carries implicit WRITE_DAC/WRITE_OWNER no ACE represents. Replaced with
  the correct argument: absent `SeRestorePrivilege`, a caller can only
  assign ownership to a SID already in its own token, so a non-admin cannot
  forge Administrators/LocalSystem ownership on a path it creates — an
  adversary who can reach this branch is already a local admin, who
  defeats the check outright via `SeTakeOwnershipPrivilege` regardless.
  Also recorded (one sentence, no code change) that the ACE-danger loop's
  existing trust of `S-1-3-4` (OWNER RIGHTS) now resolves against a
  possibly-Administrators owner rather than always the current user —
  deliberately unreviewed here, same admin-only-adversary reasoning, and
  explicitly Out of Scope.
- **Error message named the wrong object class.** `path_acl_is_private` is
  called for files too (`_safe_file`), but its owner-rejection message
  hardcoded "directory is owned by...". Changed to "path is owned by...".
- **Test names overclaimed what they prove.** Renamed
  `test_windows_private_root_still_rejects_a_genuinely_foreign_owner` →
  `test_owner_trust_rejects_a_genuinely_foreign_owner_sid` and its sibling
  to `test_owner_trust_accepts_a_trusted_system_principal` — both are pure
  `_owner_is_trusted()` calls, not `path_acl_is_private()` proofs; the old
  names would have masked the AC6 gap above from a future AC-to-test audit.
- **The cross-module import had no proof in the required gate.**
  `_windows_acl.py` imports `_windows_acl_trust` at module level, but
  `_windows_acl.py` itself is unimportable on Linux — so a future rename
  breaking that import would surface only in the advisory Windows job, not
  `ci.yml`. Added a platform-independent source-text wiring-pin test,
  `test_windows_acl_module_still_imports_the_trust_helper_from_its_sibling`.
- **The `takeown /A` test's assertion conflated two failure classes.**
  `RUNNER_TEMP`'s inherited DACL on the hosted runner is not something this
  repo observes or controls; a dangerous inherited ACE there would fail the
  test via the (untouched) ACE-danger loop, misattributed to the owner
  check this test exists to prove. Added an `icacls /inheritance:r
  /grant:r` reset before the ownership reassignment so the test isolates
  the owner branch.
- **`pytest-xdist` is a new, unpinned PyPI dependency the CI-supply-chain
  ack didn't address** (it argued only actions-pinning posture). Added a
  clause to `ci_supplychain_ack.json`'s statement recording it is
  deliberately unpinned on the same footing as this step's existing
  unpinned `pytest`/`pytest-mock`/`pytest-cov`/`coverage` — none of the
  four carries a flag/exit-code contract this job's logic depends on the
  way `diff-cover==10.3.0`'s pin does.

**Not applied:** none — every Stage 2 finding (including the low-severity
ones) was cheap enough to take as-is; no disagreement to reconcile.

## Finalization (F0) — diff-coverage gate finding applied

F0's diff-coverage gate (80% threshold on the merge-base diff) failed on
first run: `_windows_acl.py` measured 31.2% (`owner_sid_of()`'s entire
body, lines 123-137, unexercised). Root cause: the only caller was the
`takeown /A` proof test, which SKIPS on this dev machine because the
account is a member of `BUILTIN\Administrators` but the process token is
not elevated (`IsInRole(Administrator) == False` — a UAC split-token, not
a defect). This is exactly the documented "test skips on this machine,
runs in CI" exception F0.md names — but its own guidance is to add the
missing test, not weaken the gate. Checked first, empirically: does
`owner_sid_of()` genuinely need admin privilege to CALL, or only `takeown`
to REASSIGN ownership? Confirmed the former is a plain read-only ACL query
— `owner_sid_of(tmp_path)` on a directory this process just created works
with no privilege at all. Added two unprivileged win32-gated tests:
`test_owner_sid_of_reports_the_current_users_own_sid_on_a_normal_directory`
(happy path, asserts agreement with `_current_sid()`) and
`test_owner_sid_of_raises_on_a_path_that_does_not_exist` (error path). The
`takeown /A` proof test is unchanged and still the real end-to-end
Administrators-owner proof (Ledger row 3) — these two are a genuine,
independent addition, not a substitute.

## Doubt Review — findings applied

Stage 3 (`doubt-reviewer`, opus, biased to disprove): 6 doubts (1 high, 2
medium, 3 low). The reviewer explicitly tried and failed to build a working
exploit around the security widening itself (the untouched ACE-danger loop
plus the `SeRestorePrivilege` ownership constraint hold) — every surviving
doubt is a reasoning or evidence defect, not a code defect, and all six
were applied:

- **(high) The spec's own reasoning contradicted itself.** Root Cause's
  "Zero marginal capability" bullet, and the "Not applied" rejection of
  OpenAI's narrower-token-membership alternative that cited it, both still
  rested on the argument Stage 2 had already found factually wrong (the
  ACE loop did NOT already accept these SIDs — the owner check ran first
  and rejected them, which is the bug being fixed). Rewrote both to the
  surviving, correct argument (`SeRestorePrivilege` / owner-assignment
  privilege), independently verified by re-reading `_windows_acl_trust.py`
  — see Root Cause and "Plan Review — findings applied" above.
- **(medium) The falsifier pointed at an alternative the code already
  rules out.** Verified directly (not taken on the reviewer's word): the
  cancellation test calls `mod.main()` in-process with a synthetic
  `KeyboardInterrupt`, never a subprocess or real signal
  (`test_run_test_suite_faults.py:274-287`, `assert mod.main() == 130`),
  so a genuine Windows Job-Object exit-code mismatch cannot produce this
  test's failure at all — `RC_CANCELLED = 130` is a plain module constant
  in `suite_process.py`. Rewrote the Falsifier section: a red test (1)
  post-fix now means "ACL fix insufficient, or a third cause" instead of
  re-litigating the ruled-out theory.
- **(medium) The ACE-danger loop — the other half of the same function —
  has never been exercised against the runner's real ACEs**, and the new
  `takeown /A` test deliberately resets the DACL before asserting, so it
  never will be either. Added a new "ACE-danger-loop caveat" paragraph to
  the spec, and a one-line, non-gating diagnostic to
  `windows-tests.yml`'s test step: prints `path_acl_is_private()`'s actual
  verdict for the real `$LOCALAPPDATA` before the test loop runs, so the
  live PR observes this directly instead of assuming it. Tested locally
  before adding to the workflow (see Confidence Calibration probe below).
- **(low) The rejection message leaked the current-process SID into a
  public CI log** for no diagnostic value the owner SID didn't already
  provide. Dropped it from `_windows_acl.py`'s message; the
  `"neither the current user"` substring both tests match on is unchanged.
- **(low) The workflow comment claimed Linux CI validation for
  `shared/tests` under xdist that does not exist** (`ci.yml` runs all
  three directories serially). Corrected the comment, and added guidance
  that a timing-only flake under `-n 4` is answered by dropping to `-n 2`,
  never by re-deselecting the two now-fixed tests.
- **(low) No comparison existed between the xdist run's pass count and a
  serial baseline**, so "green under `-n 4`" wasn't pinned to "the same
  tests as the serial run". Addressed empirically — see Ledger row 9.

## Confidence Calibration

- **Boundaries touched:** none.
- **Empirical probes run:**
  1. Read the live workflow file as it exists on `main`, confirmed the
     exact loop structure (3x `uv run --with ...`, no `-n` flag, two
     `--deselect` flags) the goal section describes.
  2. Read `shipwright_test_config.json`'s `suite.xdist` allowlist and
     `run_test_suite.py`'s `build_command` to confirm the invocation shape
     to mirror (`--with pytest-xdist` provisioned explicitly, `-n <count>`
     passed explicitly, never `-n auto`).
  3. Recomputed the diff-driven risk detectors against the changed files —
     only `ci_supplychain` is `True` (the workflow file); the two Python
     files under `shared/scripts/lib/` are shared infra (already full-test
     required at medium).
  4. Read `trg-eed74a42`'s full triage text, then traced both failing
     tests' actual call paths through `f0_cpu_lease` →
     `host_resource_lease()` → `_safe_runtime_root` →
     `path_acl_is_private()`, confirming both fail at the identical
     ownership check before either test's own assertions are reached.
  5. Ran both previously-deselected tests locally (native Windows) against
     the *unmodified* code — both **pass** locally (this machine's own
     account owns its own `LOCALAPPDATA`, so the check never rejects it —
     the defect is CI-runner-specific, matching the triage card's own
     framing of "surfaced only in that job").
  6. Wrote a regression test for `path_acl_is_private` using `takeown /A`
     (the same primitive this workflow's own WSL-stub-removal step already
     uses) to reproduce an Administrators-owned directory for real; ran it
     against the *unmodified* code first and confirmed it fails
     (`AssertionError` — red, pinning the root cause) before writing the
     fix.
  7. Wrote a pure-function negative test (`test_owner_trust_rejects_a_genuinely_foreign_owner_sid`,
     renamed from its original name per Stage 2 code review — see "Code
     Review — findings applied") confirming the fix does not accept an
     arbitrary foreign SID.
  8. Ran the full restructured `windows-tests.yml` step body locally
     (single provisioning, `-n 4` on `shared/tests`, no `--deselect`) — see
     Ledger.
  9. Confirmed `pytest.skip` (no privilege to reproduce the Administrators-
     owner scenario) is the wrong disposition unconditionally: hardened the
     `takeown /A` test to `raise AssertionError` (not `pytest.fail`, which
     CodeQL flags as an implicit return and blocks automerge) when `CI` is
     set, so a broken reproduction on the actual runner fails the run
     instead of skipping green. Also removed the `skipif(win32)` guard from
     the negative (still-rejects-a-foreign-owner) test — it is pure string
     comparison, so it now runs in the required Linux gate (`ci.yml`) too,
     not only in this advisory Windows job — and added its positive
     counterpart (`_owner_is_trusted` accepts a trusted-system SID),
     equally platform-independent.

**Predicted post-change wall clock (falsifiable target, not a promise):**
`shared/tests` dominates (see Goal §1) at ~22-24 minutes serial. `-n 4`
cannot yield a clean 4x (test collection, fixture setup, and Windows
filesystem I/O do not scale linearly, and this workflow has no history of
measuring xdist speedup on this specific host shape) — a realistic target
is roughly 6-10 minutes for `shared/tests`, plus ~1-2 minutes for the two
serial directories (unchanged) and the WSL-stub-removal/provisioning steps
(unchanged), for a **predicted total step time of roughly 10-14 minutes**,
down from 24-28. If the live run comes in well outside that band, that is
new information worth recording, not just "it got faster."
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | The restructured single-provision, xdist-on-`shared/tests` step collects and passes locally on native Windows, all three directories, no `--deselect` | tested | local run of the exact restructured command: `shared/scripts/tools/tests` 535 passed/8 skipped/2 deselected(marker-only); `shared/tests` confirmed 4/4 xdist workers engaged (`gw0`..`gw3` in output) |
  | 2 | `shared/scripts/tests` and `shared/scripts/tools/tests` still run serially (no `-n` passed) | tested | inspected the emitted pytest command per directory in the local run's own stdout — no `-n` flag for either |
  | 3 | `path_acl_is_private` accepts an Administrators-owned directory (`takeown /A` reproduction) | tested (skips only outside CI; hard-fails under CI) | `test_windows_private_root_accepts_administrators_owned_directory`; on this non-admin dev account it skips ("current account cannot reassign ownership... needs runneradmin-equivalent privilege"), but `raise AssertionError` (not a swallow) if that same failure happens with `CI` set — so the actual `windows-latest` job (runs as admin-equivalent `runneradmin`) either proves it for real or fails the run, never skips green; confirmed live post-push |
  | 4 | `path_acl_is_private`'s owner check still rejects a genuinely foreign SID, and separately accepts a trusted-system SID | tested | `test_owner_trust_rejects_a_genuinely_foreign_owner_sid` and `test_owner_trust_accepts_a_trusted_system_principal` — both pure `_owner_is_trusted()` calls, no OS privilege, no `skipif` (run in the required Linux gate too), passing locally. Renamed from `test_windows_private_root_...`/`test_windows_acl_owner_check_...` per Stage 2 code review — the old names overclaimed a `path_acl_is_private()`-level proof these pure calls don't give (see row 11) |
  | 5 | Pre-fix, the Administrators-owner scenario is rejected (root-cause pin) | tested | ran the new `takeown /A` test against the unmodified code before applying the fix — failed with the exact "not owned by the current user" `AssertionError` |
  | 6 | Both previously-deselected tests pass with no `--deselect` applied | tested | `pytest shared/scripts/tools/tests -k "test_main_cancellation... or test_the_f0_cli_stops..."` → `2 passed` |
  | 7 | Full `shared/scripts/tools/tests` has no regression from the `_windows_acl.py` change (incl. the 5 new tests this fix added: the `takeown /A` positive proof, the two pure `_owner_is_trusted()` cases, the function-boundary reject proof, the wiring-pin test) | tested | full directory run, definitive count: 535 passed/8 skipped/2 deselected(marker) — four of the five new tests run and pass unconditionally, the `takeown /A` test is one of the 8 skips on this non-admin dev account (see row 3) |
  | 9 | `shared/tests` under `-n 4` is not flaky (xdist test-isolation risk raised by external review), AND runs the identical test set the serial baseline does (Stage 3 doubt review — a prior pass recorded the xdist count with no serial comparison) | tested | run twice independently to completion with zero failures: once as part of the full 3-directory local run (part of Ledger row 1), once standalone with the exact production `-m "not slow and not cross_plugin"` filter (8593 passed, 28 skipped, 356.47s) — plus a third partial run confirming 4/4 workers engage (`gw0`..`gw3`). Collection-only run with the identical filter reports `8621/8647 tests collected (26 deselected)`, matching **exactly** the last live serial Windows CI run's own summary (GH Actions run 31180329620: `8604 passed, 17 skipped, 26 deselected` — 8604+17=8621, same total, same deselect count). The 11-test passed→skipped shift between serial and xdist (17 vs 28) is consistent with concurrency-aware skip guards reacting to parallel execution, not test loss — no test disappears from either run's total |
  | 10 | The restructured `bash -c` wrapper fails closed: a failure in an earlier directory is not masked by a later directory succeeding | tested | ran the wrapper with a deliberately-failing first directory (`pytest -k "matches_nothing"`, pytest exit 5) — script exit code 5, second directory never reached |
  | 11 | `path_acl_is_private()` itself — not just the pure `_owner_is_trusted()` helper — rejects a genuinely foreign owner (AC6 at the actual function boundary) | tested | `test_windows_private_root_rejects_a_spoofed_foreign_current_user` (win32-gated): monkeypatches `_current_sid` on a directory the test process genuinely owns, asserts `path_acl_is_private()` returns `(False, ...)`. Added per Stage 2 code review: without it, deleting the owner check outright — the mini-plan's own rejected alternative — would leave every prior test green |
  | 12 | A future rename breaking `_windows_acl.py`'s import of `_windows_acl_trust` would be caught even though `_windows_acl.py` cannot itself be imported on Linux | tested | `test_windows_acl_module_still_imports_the_trust_helper_from_its_sibling` — reads `_windows_acl.py`'s source text and asserts the import line and `_owner_is_trusted(` call are present; runs on any platform since it never imports the ctypes-gated module. Added per Stage 2 code review (sibling-import blind spot: nothing in the required Linux gate exercises this cross-module wiring otherwise) |
  | 13 | `owner_sid_of()` reports the current user's own SID on a normal, self-owned directory, and raises on a nonexistent path (F0 diff-coverage gate — its body was otherwise exercised only by the privilege-skipped `takeown /A` test) | tested | `test_owner_sid_of_reports_the_current_users_own_sid_on_a_normal_directory` and `test_owner_sid_of_raises_on_a_path_that_does_not_exist`, both win32-gated, no admin privilege required (a read-only ACL query, unlike `takeown`) |
  | 8 | GitHub Actions' `windows-latest` runner (real `runneradmin` account) actually accepts its own Administrators-owned `LOCALAPPDATA`, completes the job green, faster than the 24-28 min baseline, with both previously-deselected tests now passing | untestable | requires-external-nondeterministic-service (verified post-push by observing the live CI run's wall-clock, pass/fail state, and the two specific test outcomes) |

- **Confidence-pattern check:** asymptote (depth) — traced to the actual
  owner-SID comparison and the actual call path both failing tests share,
  not "CI looks flaky on Windows"; coverage (breadth) — the perf cause (no
  parallelism, triple provisioning) and the correctness cause (ownership
  check) are independently probed, and the correctness fix's negative case
  (still-rejects-foreign-owner) guards against silently widening a
  security check while fixing it.

## Verification (medium+)

- **Surface:** none (CI/workflow-performance + internal-tooling security
  check; no web/UI/API/store/SSE surface touched).
- **Justification:** Backend-affects-Frontend rule N/A. Verified via native-
  Windows local runs of the exact restructured pytest invocation and the
  new/modified `_windows_acl.py` tests, plus the live PR's own Windows
  Actions run (external, non-deterministic — see Ledger row 8).
- **Evidence path:** `.shipwright/runs/iterate-2026-08-07-windows-ci-perf/surface_verification.json`
  (surface=none + justification).
