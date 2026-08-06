# Iterate Spec: write-lock-primitives

- **Run ID:** iterate-2026-08-06-write-lock-primitives
- **Type:** bug
- **Complexity:** medium
- **Status:** draft
- **Triage card:** `trg-dc013d82` (P2.19d, split from `trg-79102ee3`) — findings 10 / 20 / 24
- **Evidence:** `.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`

## Goal

Close three latent defects in the two write/lock primitives every
`shipwright_*` state writer routes through: `durable_atomic_write` silently
strips a file's POSIX permissions on every rewrite, the Windows
sharing-violation retry misses `ERROR_LOCK_VIOLATION`, and the blocking
`FileLock` can hang a session forever with no diagnostic.

## Root-Cause Investigation (F-debug — BUG path, Iron Law)

None of the three is a runtime crash with a stack trace, so **Phase 1 has no
error text to read**. All three are *silent* defects found by static audit and
re-measured 2026-08-05. Stated plainly rather than dressed up as a traceback.

### Finding 20 — POSIX mode is discarded on every publish

- **Symptom vs expected.** Observed: a file rewritten through
  `durable_atomic_write` ends up mode `0600`. Expected: it keeps the mode it
  had. `git` sees nothing — only the x-bit is tracked — so the loss is
  invisible in review and in history.
- **Phase 3 (regression?).** **Not a regression.** `git log` on the file:
  the primitive was introduced in `2c183c3b` (#234) with `mkstemp` +
  `os.replace` and has never carried the mode. Present since day one.
- **Phase 4 — root cause (one sentence).** `tempfile.mkstemp` creates the temp
  file `0600` by design and `os.replace` publishes the **source inode**, mode
  included, so the destination's own mode is overwritten by the temp file's at
  `atomic_write.py:163` — the mode is never read, never carried.
- **Error site vs error source.** The site is `os.replace`; the source is the
  *missing* step between `mkstemp` and the rename. The fix is at the source.

### Finding 10 — `ERROR_LOCK_VIOLATION` (33) falls out of the retry

**The card's stated symptom does not reproduce, and this run measured why.**

- **Claimed symptom.** A byte-range lock on the destination makes `os.replace`
  raise `PermissionError(winerror=33)`, which falls out of the retry.
- **Phase 2 (reproduce) — FAILED, twice.** Probed on this Windows 11 host
  (`scratchpad/probe33.py`, 2026-08-06): a destination merely held open gives
  winerror **5**; a destination held open *and* byte-range locked also gives
  **5**. `iterate-2026-07-27-run-unit-parallel-race` ran the same probe and
  **declined this exact suggestion on that evidence**. The reason is structural:
  holding a byte range requires holding the file open, and the open handle alone
  already yields 5, so 33 never gets a chance to surface on local NTFS.
- **Phase 3 (regression?).** **Not a regression.** `_SHARING_VIOLATION_WINERRORS`
  was introduced as `{5, 32}` in `0b4c9b8b` (#471) — never narrowed.
- **Phase 4 — root cause, as far as it goes.** `atomic_write.py` gates the retry
  on `exc.winerror in _SHARING_VIOLATION_WINERRORS`. CPython's `PC/errmap.h`
  does map 33 to `EACCES` and so to `PermissionError`, so a host that reports it
  *would* fall out of the retry. That is a real code-reading observation about a
  path this host does not take.
- **Disposition: add 33, labelled honestly as defence in depth.** The cost is
  bounded and already accepted for the far more ambiguous 5 (at worst the same
  short stall); the payoff on a filesystem that does report 33 — SMB, a network
  share, a different Windows build — is a write not silently lost. What this run
  must NOT do is bank it as a fixed defect: the audit's consequence claim is
  falsified, and the code and this spec say so.
- **What the probe DID find (new, and not fixed here).** A *read* of a
  byte-range-locked region fails inside the read syscall rather than
  `CreateFile`, so CPython raises an errno-only `PermissionError` with
  `winerror` **None** — verified through `Path.read_text`, which is exactly what
  `durable_read_text` calls. `None` matches no code set, so the read-side retry
  re-raises instead of retrying. That is a genuine gap in the same predicate,
  discovered by probe during this run, and it is **deliberately left for its own
  card**: it is the read side, and treating a `winerror`-less `PermissionError`
  as transient trades a denied read for a full read-budget stall — a decision
  that deserves its own run, not a rider on this one.

### Finding 24 — the blocking `FileLock` has neither a bound nor reentrancy

- **Symptom vs expected.** Observed: a contended or re-entered `FileLock` never
  returns — POSIX `flock(LOCK_EX)` blocks indefinitely, Windows spins a 1 ms
  loop forever. Expected: bounded wait, then a `LockTimeout` naming the lock.
- **Phase 3 (regression?).** **Not a regression.** The class was extracted
  *verbatim* in `b8050b57` (#239) from the two call-site copies in
  `record_event.py` and `triage.py`; the unbounded loop came with it and
  predates the extraction.
- **Phase 4 — root cause.** `file_lock.py:154-164` has no deadline in either
  branch and no record of what this process already holds, so (a) a waiter
  cannot give up and (b) a second acquisition of the same path from the same
  thread waits on a lock only that thread can release — a self-deadlock with
  no diagnostic. The sister context manager `file_lock()` in the same module
  takes a hard `timeout_seconds=5.0` and documents why; the class was simply
  never given the same treatment.
- **Where it bites (traced 2026-08-05).** The lock sits on hook paths (event
  log, iterate timings) *and* on `setup_iterate_worktree.py` step 5 — the
  triage sweep, which runs in every iterate. That is precisely where a silent
  hang is indistinguishable from a session death.
- **Honest scope note.** The audit proved there is **no double acquisition in
  the code today**. Reentrancy here is a guardrail against a future one, not a
  live defect. The *timeout* is the live exposure.

## Acceptance Criteria

- [ ] **AC-1** On POSIX, `durable_atomic_write` onto an existing file whose mode
      is `0o644` leaves the file at `0o644` (today: `0o600`). Verified by
      `stat().st_mode & 0o7777` before and after.
- [ ] **AC-2** On POSIX, `durable_atomic_write` onto a **non-existent** path
      leaves the file at `mkstemp`'s `0o600` — unchanged, deliberately not
      guessed. Pinned so the "carry the mode" rule cannot silently grow into
      "invent a mode".
- [ ] **AC-3** A destination that cannot be `stat`-ed or `chmod`-ed does not
      fail the write: the bytes still land and the call returns normally.
- [ ] **AC-4** With the Windows branch forced, an operation raising
      `PermissionError(winerror=33)` is retried within the budget and succeeds
      on a later attempt; the retry counter increments. A `winerror` outside the
      set (e.g. 13) still re-raises immediately.
- [ ] **AC-5** `FileLock` acquired on a path already held by **another thread**
      raises `LockTimeout` within the configured `timeout_seconds` instead of
      blocking forever; the message names the lock path and the wait.
- [ ] **AC-6** `FileLock` re-acquired on the same path from the **same thread**
      (nested `with`, including through two different `FileLock` instances)
      enters immediately, and the lock is released only when the outermost
      block exits — a concurrent acquirer is still excluded while the inner
      block runs.
- [ ] **AC-7** `timeout_seconds=None` restores the historical unbounded block —
      reachable only by asking for it explicitly.
- [ ] **AC-8** Existing behaviour preserved: mutual exclusion between threads,
      `__enter__` creating a missing parent directory, `self._fp` reset on exit.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** Both modules are internal write/lock primitives with
  no entry in `shipwright_sync_config.json`'s `file_to_fr_map`; the change fixes
  latent defects in existing behaviour and introduces no user- or
  system-observable capability. `affected_frs` is empty, so the F5b no-FR branch
  (`change_type`) applies.

## Out of Scope

- **Widening `touches_shared_infra`.** Its patterns are Next.js-shaped
  (`src/lib/`, `src/components/ui/`) and structurally cannot match this Python
  monorepo's `shared/scripts/lib/`. Real gap, separate decision — widening a
  risk-flag surface needs the message/diff parity discipline documented in
  `risk_detectors.py`, not a drive-by edit inside a bug fix.
- **Reentrancy for the sister `file_lock()` context manager.** It already has a
  hard 5 s timeout, so a nested acquisition there fails loudly rather than
  hanging; it is not made reentrant. It *is* touched, though — see below.
- **Per-call-site timeouts.** Every caller keeps the new default; the parameter
  exists so a caller that knows its hold is short can tighten it later.
- **`FileLock.__enter__`'s `open(path, "w")` truncation.** It truncates the lock
  file *before* acquiring. Harmless today (the sidecar carries no content) and
  untouched here.

## Design Notes

**Why a third file.** `atomic_write.py` is 299 lines against the constitution's
300-line source limit, so this change cannot be made inside it without creating
a new bloat crossing. A pure extraction was rejected — the operator's split of
`trg-79102ee3` deliberately keeps moves out of fix runs, and `_is_windows` /
`_fsync_parent_dir` are monkeypatched or imported from 13 places. Instead a new
leaf `shared/scripts/lib/durable_publish.py` holds only what this change is
already touching: the winerror set (finding 10 edits it) and the new mode
carrier (finding 20 adds it). Nothing is relocated that this diff does not
otherwise modify. `_SHARING_VIOLATION_WINERRORS` stays resolvable on
`atomic_write` as an alias so existing name lookups do not break.

**Why the `FileLock` default is 600 s, not the sister's 5 s.** The sister guards
a single short append. `FileLock`'s longest legitimate holder is the triage
sweep in `sweep_outbox.py`, whose critical section chains several git
subprocesses each capped at `HOOK_GIT_TIMEOUT` (120 s). A 5 s bound would turn a
slow-but-progressing sweep into a hard failure on every iterate's worktree
setup. 600 s = 5 × the longest single sub-operation: strictly above any
plausible healthy hold, while still converting "hangs until the operator kills
the session" into "fails in a bounded time, naming the lock".

**Why the two poll loops were unified (a scope call made during build).** Giving
`FileLock` a bounded wait meant writing a poll loop, and the module already had
two — `_acquire_posix` and `_acquire_windows`, serving the sister `file_lock()`.
Shipping a third would have left the module with two implementations of the same
thing, which is precisely how one primitive ended up with a bound and the other
without. Both sisters were therefore deleted and `file_lock()` now calls the same
`_acquire_bounded`. Verified safe before doing it: neither helper has a single
reference outside this module, and none of the 16 `file_lock()` call sites passes
`poll_interval`. Behaviour for the sister is preserved — same 5 s default, same
`LockTimeout` — with **three** recorded deltas, none of which any call site can
observe today:

1. `poll_interval` is now the backoff *ceiling* rather than a flat interval, so
   an almost-free acquisition no longer always pays 50 ms. Strictly faster for
   every caller, since none passes the parameter at all; the one hypothetical
   case where it could be slower is `poll_interval < 1 ms`, below the shared
   1 ms initial step.
2. `timeout_seconds=None` now means *unbounded* where it previously raised
   `TypeError` (`monotonic() + None`). Consistent with the class, and reachable
   only by explicitly asking for it.
3. `NaN` / `inf` / negative / non-numeric `timeout_seconds` now raise
   `ValueError` instead of being accepted. `NaN` in particular used to produce a
   silently unbounded wait, since every deadline comparison against it is false.

Deltas 2 and 3 were missed in the first draft of these notes and added after the
Stage-1 spec review caught the omission. Verified across all 16 call sites: every
one passes a plain positive float or nothing.

**Why reentrancy is keyed on path, not instance.** The self-deadlock the card
describes is two *different* `FileLock(path)` instances on one call stack —
`record_event` inside a sweep, say. A per-instance flag would not see it. The
registry is keyed on the canonicalised **absolute** path and records the owning
thread, so a different thread is still excluded and still waits on the real OS
lock.

**Why the registry ended up in its own module (Stage-2 outcome).** It was inline
in `file_lock.py` until the Stage-2 review pointed out that `_host_resource_locking`
already solves this exact problem one directory over — a process-scoped ownership
registry keyed on a canonicalised path — and that this copy had dropped two of
its safety properties. Adding them back did not fit: `file_lock.py` was at the
300-line ceiling, and this was the *third* time in one iterate that the ceiling
forced prose to be compressed rather than a decision to be recorded. So the
registry moved to `file_lock_registry.py`, deliberately mirroring the sibling's
shape, and `file_lock.py` dropped to 283 with room to state its invariants. The
two properties recovered in the move:

- **`realpath`/`abspath`, not `Path.resolve()`.** On the pinned 3.11 interpreter
  Windows' `resolve(strict=False)` swallows only `FileNotFoundError`, so a
  deny-ACL parent or a dead UNC share raises *out of `FileLock.__init__`* — a
  constructor callers may reasonably treat as infallible, and which was
  infallible before this change. `realpath` degrades instead. Absolutising also
  closes a genuine exclusion hole: two instances built from the same *relative*
  path in different working directories would otherwise share a key while
  locking different files, and the reentrant short-circuit would skip the OS
  lock for a lock the thread does not hold. The same absolute path is now used
  for both the key and the `open()`.
- **A pid guard.** A `fork` copies the registry but not the locks it describes,
  and the child's main thread inherits the forking thread's ident — so without
  the guard the child would "re-enter" a lock it does not hold and its exit
  would release the *parent's* (the handles share one open file description).
  Nothing in this repo forks today; the sibling module guards it anyway, and two
  registries disagreeing about something this sharp is how the next bug starts.

**The loader contract broke, and only the doubt review found it (high).** Giving
`file_lock` and `atomic_write` each a sibling import falsified a constraint
stated in two places: `shared_lib_loader`'s docstring ("only safe for lib modules
with no intra-package imports") and `triage_header`'s, which cited *those two
modules by name* as leaves that satisfied it. Reproduced rather than reasoned
about (`scratchpad/probe_loader.py`): with `sys.modules['lib']` bound to a decoy —
exactly what a plugin test session leaves behind — the fallback died with
`ModuleNotFoundError: No module named 'file_lock_registry'` / `'durable_publish'`.

That is a `triage.py` write path, and the in-process triage producers wrap their
append in `except Exception`, so it would have shipped as **silently lost
findings**, not as a crash. None of the four test roots this run had executed
could see it: the fallback only fires once some *other* `lib` has claimed the
name.

Fixed in the loader rather than by inlining the two symbols back: it now loads
into a private **package** whose `__path__` is `shared/scripts/lib`, so a sibling
import resolves inside it and never touches `lib`. `shared/scripts/lib` is
deliberately still NOT put on `sys.path` — it holds `config.py` and `state.py`,
so that shortcut would relocate the very collision the loader exists to survive.
The limitation is now gone rather than merely dodged, and both docstrings say so.

**Why a stuck lock is NOT swallowed at worktree setup.** Giving `FileLock` a
bound means `sweep_outbox_to_branch` — which documents "never raises for an
expected condition" — can now raise `LockTimeout` into `setup_iterate_worktree`
step 5, on the critical path of every iterate. Stage 2 flagged the contract as
silently falsified, which it was. The fix is the *documentation*, not a catch:
unlike `op_in_progress` or `staged_changes`, a canonical lock held for the full
600 s is a host fault, not a benign state to skip past, and the pre-change
behaviour was to hang there forever. Failing loudly with a diagnostic naming the
lock is the entire point of bounding it. Both that docstring and
`reconcile_triage`'s now say so explicitly.

The doubt review then sharpened this and was right on the sharper point: it is
not loud-vs-silent, it is that `LockTimeout` is a `RuntimeError` and
`setup_iterate_worktree.main()` catches only `(GitError, OSError)`, so the one
exception this change adds was the one exception that bypassed the tool's JSON
error contract — after the worktree and branch already exist. `LockTimeout` now
**joins that tuple** with its own `reason`, which keeps the failure loud and
non-zero while restoring the contract every other step-5 failure already honours.

**Where the bound genuinely does NOT help, stated plainly.** The card motivates
this by the hook paths (event log, iterate timings), where a hang is
indistinguishable from a session death. Claude Code kills a hook well before
600 s, so on precisely those paths the bound is never reached and behaviour is
unchanged — those callers already had an external bound. The 600 s figure is
derived from `sweep_outbox`, a different call site. The change is still worth
making (the sweep and the worktree path are real, and the reentrancy guardrail is
path-independent), but the hook-path motivation in the card does not survive
contact with the runtime, and pretending otherwise would be the overclaim this
run has already had to correct once.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| n/a | n/a | n/a |

No serialized format changes. `durable_atomic_write`'s *bytes* contract is
untouched — only the published file's POSIX mode and the retry predicate
change. `FileLock` changes control flow, not any on-disk format. The
`touches_io_boundary` flag does not fire and no Boundary Probe is owed.

## External Code-Review Findings (medium+ cascade)

Run over the full diff after the internal cascade. `openai` = **revise**,
`deepseek` = **unavailable** (one leg degraded; the cascade still ran, so this is
not a Branch-B fallback). It found **three real defects introduced by the
doubt-review remediation itself** — a useful reminder that a fix pass needs its
own review, not just the thing it fixed.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | **high** | `release()` never called `_reset_after_fork()`. A forked child inherits both the entry and the forking thread's ident, so its exit matches as owner and unlocks + closes a handle sharing an open file description with the parent — dropping a lock the parent still holds. | **accepted-and-fixed.** The guard was on `enter_reentrant` and `register` only; guarding just the acquire paths guards nothing. Added to `release()` under the same lock, plus `test_a_forked_child_does_not_release_the_parents_lock`. This is the sharpest bug in the run and it was introduced *by the fix for doubt 1*, after two reviewers had already passed the module. |
| 2 | medium | `_state()` had a check-then-create race: two threads could each build a state object and one overwrite the other, stranding any lock registered in the discarded one — whose owner would then fail to re-enter and wait out its full timeout. | **accepted-and-fixed.** Now `sys.modules.setdefault(...)`, which is atomic, so exactly one candidate wins and every caller gets the winner. |
| 3 | medium | `_RUNNER_FILES` in `test_f0_cli_diff_coverage_e2e.py` copies `file_lock.py` but not its new sibling `file_lock_registry.py`. | **accepted-and-fixed.** Exactly the class of breakage already fixed once for `atomic_write`/`durable_publish` in this same diff — I updated one vendoring list and missed the second in the same tuple. Both siblings are now listed, with a comment recording that the first pass got it half right. |
| 4 | low | AC-3's refused-`stat` branch was covered only by calling the carrier directly, so an integration regression specific to that arm would not be caught. | **accepted-and-fixed.** Added `test_write_survives_an_unstattable_destination`, end-to-end through `durable_atomic_write`. |

## Confidence Calibration

- **Boundaries touched:** none — no serialized format changes (see *Affected
  Boundaries*). What this diff does touch is a *platform* boundary (POSIX mode
  bits, Windows error codes) and a *concurrency* boundary (lock ownership), so
  the probes below target those instead.

- **Empirical probes run:**
  1. **Does a byte-range lock really surface as winerror 33?** (`probe33.py`,
     this host, Windows 11 / local NTFS) — **NO.** Destination merely held open
     → winerror **5**; held open *and* byte-range locked → winerror **5**. The
     card's stated consequence for finding 10 does not reproduce, and this is
     the *second* time it has failed to (`iterate-2026-07-27-run-unit-parallel-race`
     declined it on the same evidence). Outcome: 33 still added, but relabelled
     in code and spec as bounded defence-in-depth, not a measured fix.
  2. **Then what DOES escape the retry predicate?** (`probe_read.py`) — a read
     of a byte-range-locked region raises `PermissionError` with `winerror`
     **None**, verified through `Path.read_text`, which is exactly what
     `durable_read_text` calls. No code set can match `None`, so the read side
     re-raises rather than retrying. New finding, deliberately unfixed here,
     filed as its own card.
  3. **Do the new lock tests actually discriminate?** (`discriminate.py`, the
     verbatim pre-fix `FileLock`) — AC-5 → **BLOCKED FOREVER**, AC-6 →
     **SELF-DEADLOCK**, AC-7 → **ACCEPTED NaN**. This doubles as the Phase-2
     reproduction for finding 24 on this host, and it was necessary: unlike the
     `durable_publish` tests, the `file_lock` tests were never observed red
     before the implementation landed.
  4. **Does anything else vendor `atomic_write.py` by path?** Repo-wide sweep
     for path literals → exactly two E2E fixtures, both found by their own
     failure (3 red tests) and both fixed. No third site exists.
  5. **Regression sweep across every root that consumes these primitives:**
     `shared/tests` 8142 passed, `shared/scripts/tools/tests` 490 passed,
     `shared/scripts/tests` 365 passed, `plugins/shipwright-run/tests` 393
     passed.
  6. **Does the shadowing-proof loader still work?** (`probe_loader.py`, after
     the doubt review) — **NO, it was broken by this change**, reproduced with
     `sys.modules['lib']` bound to a decoy: `ModuleNotFoundError` for both
     `file_lock_registry` and `durable_publish`. Fixed and re-probed green. This
     is the probe that mattered most, and it exists only because a reviewer
     attacked the import shape rather than the logic.
  7. **What does `msvcrt.locking` raise for contention vs a fault?**
     (`probe_msvcrt.py`) — contention is `PermissionError`/EACCES, a dead
     descriptor is a plain `OSError`/EBADF, and NEITHER carries a winerror. So
     the Windows branch could be narrowed by exception type, mirroring POSIX,
     instead of swallowing every `OSError` and polling a real fault for 600 s.
  8b. **F0 went RED on a gate nothing else runs.** The loader fix carried a
     second `# nosemgrep` for the non-literal-import rule, and this repo ratchets
     inline suppressions *per rule, repo-wide* (`a9d60100`, #573 — the very
     commit this branch was cut from): 9 allowed, 10 present. Fixed the way the
     guard asks for first — removed the new suppression rather than raising
     `max_sites` — by routing both resolution paths through one `_import`
     helper, so the count stays flat and the rationale lives in one docstring.
     Learned 19 minutes into a suite run; `inline_suppressions_cli.py check`
     answers the same question in about a second and belongs before F0.
  8. **The four plugin roots the earlier sweep missed** — the doubt review noted
     that the in-process triage producers living in `shipwright-test`,
     `-security`, `-compliance` and `-adopt` are exactly where probe 6's failure
     bites, and that this run's evidence could not have seen it. All four run
     green: security 893, adopt 602, test 243, compliance 1628 (+5 skipped).
     **12,756 tests across all eight roots.**

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | A rewrite carries the destination's existing mode (AC-1) | tested | `test_atomic_write.py::test_rewrite_keeps_the_files_existing_mode` PASSED (CI/POSIX; skipped on the Windows dev host) |
  | 2 | A first write stays at `mkstemp`'s 0600 — carry, never invent (AC-2) | tested | `test_atomic_write.py::test_first_write_keeps_mkstemps_private_mode` PASSED (CI/POSIX) |
  | 3 | The mode bits selected are the destination's, masked to 0o7777 | tested | `test_durable_publish.py::test_carries_the_destinations_exact_mode_bits` PASSED (every host — closes the POSIX-only gap in rows 1-2) |
  | 4 | A refused mode carry never fails the write, and IS counted (AC-3) | tested | `test_atomic_write.py::test_write_survives_a_refused_mode_carry` PASSED — drives a refused `fchmod` end-to-end and asserts the bytes land, the call returns, and `mode_carry_failures() == 1` |
  | 4b | A carrier that RAISES still unlinks the temp | tested | `test_atomic_write.py::test_a_raising_carrier_still_unlinks_the_temp` PASSED. Split out in Stage-1 review: it asserts the write FAILS, so it is defence-in-depth for a shape the implementation forbids — **not** AC-3 evidence, which it was mislabelled as in the first draft |
  | 5 | A refused `fchmod` is counted, not silently swallowed | tested | `test_durable_publish.py::test_a_failed_carry_is_counted_not_raised` PASSED |
  | 5b | A refused `stat` (mode unknowable, not absent) is counted too — AC-3's other half | tested | `test_durable_publish.py::test_an_unstattable_destination_is_counted_too` PASSED. Added after Stage 1 flagged the branch as present-but-unexercised; no row had claimed it, but a symmetric branch with only one half tested is how the next asymmetry gets introduced |
  | 6 | An absent destination is "nothing to carry", not a failure | tested | `test_durable_publish.py::test_missing_destination_has_no_mode_to_carry` PASSED |
  | 7 | The carry is applied BEFORE the fsync that lands the bytes | tested | `test_atomic_write.py::test_mode_is_carried_before_the_fsync` PASSED (ordering spy) |
  | 8 | No-op where `os.fchmod` does not exist (Windows) | tested | `test_durable_publish.py::test_no_op_where_fchmod_does_not_exist` PASSED (attribute deleted, so POSIX CI runs the Windows branch too) |
  | 9 | Winerror 33 is in the sharing-violation set (AC-4) | tested | `test_durable_publish.py::test_lock_violation_is_a_sharing_violation_code` PASSED |
  | 10 | A winerror-33 failure is retried end-to-end and each retry counted, not raised on first contact (AC-4) | tested | `test_durable_publish.py::test_replace_retries_winerror_33` PASSED — 3 attempts, `sharing_violation_retries() == 2` (Windows branch forced, so it runs on Linux CI). Renamed in Stage-1 review: the old name dressed an injected code up as a measured byte-range-lock scenario |
  | 11 | A winerror outside the set still re-raises immediately | tested | `covered-by-existing-test` — `test_atomic_write_windows_retry.py` already pins the non-transient code path; 8 passed unmodified |
  | 12 | The `atomic_write` alias IS the leaf's frozenset, not a fork | tested | `test_durable_publish.py::test_atomic_write_alias_is_the_leaf_frozenset_not_a_fork` PASSED (identity, not equality) |
  | 13 | A contended `FileLock` raises `LockTimeout` inside its budget (AC-5) | tested | `test_file_lock.py::test_timeout_raises_instead_of_blocking_forever` PASSED; discriminates (old → blocked forever) |
  | 14 | The `LockTimeout` message names the lock and the wait (AC-5) | tested | same test — asserts `str(lock_path) in message` AND `"waited" in message`. The wait half was claimed but unasserted in the first draft; Stage-1 review caught it and the assertion was added rather than the claim dropped |
  | 15 | `timeout_seconds=0` is exactly one non-blocking attempt (AC-7) | tested | `test_file_lock.py::test_zero_timeout_is_one_non_blocking_attempt` PASSED |
  | 16 | `timeout_seconds=None` restores the unbounded block (AC-7) | tested | `test_file_lock.py::test_none_timeout_restores_the_unbounded_block` PASSED |
  | 17 | NaN / inf / negative / non-numeric timeouts are rejected (AC-7) | tested | `test_file_lock.py::test_invalid_timeout_is_rejected` PASSED (4 params); discriminates (old → accepted NaN) |
  | 18 | Same-thread nested acquisition enters immediately (AC-6) | tested | `test_file_lock.py::test_same_thread_reentry_enters_immediately_and_holds_until_outermost_exit` PASSED; discriminates (old → self-deadlock) |
  | 19 | Another thread stays excluded through the inner block AND after it exits (AC-6) | tested | same test — two `_acquire_from_another_thread(...) == "timeout"` assertions, then `"acquired"` after the outermost exit |
  | 20 | An exception inside a nested block still releases the lock | tested | `test_file_lock.py::test_exception_inside_a_nested_block_still_releases` PASSED |
  | 21 | A timed-out instance leaks nothing and still works afterwards (AC-8) | tested | `test_file_lock.py::test_instance_is_clean_after_a_timeout` PASSED |
  | 22 | Pre-existing behaviour preserved: mutual exclusion, parent mkdir, reuse, call-site aliasing (AC-8) | tested | `covered-by-existing-test` — the 4 original `test_file_lock.py` tests pass unmodified |
  | 23 | The sister `file_lock()` keeps its timeout and exception after sharing the loop | tested | `covered-by-existing-test` — its 16 call sites are exercised across `shared/tests` (8134 passed) and `plugins/shipwright-run/tests` (393 passed) |
  | 24 | The E2E coverage fixtures carry the new leaf | tested | `test_f0_diff_coverage_e2e.py` + `test_f0_cli_diff_coverage_e2e.py` — 3 failed before the fixture fix, 490 passed after |
  | 25b | The registry key is independent of the working directory (exclusion-critical) | tested | `test_file_lock_registry.py::test_key_is_independent_of_the_working_directory` PASSED — same key from parent and child cwd |
  | 25c | `lock_key` never raises, so `FileLock.__init__` stays infallible | tested | `test_file_lock_registry.py::test_key_does_not_raise_on_an_unresolvable_path` PASSED |
  | 25d | Reentrancy is per-thread — a second thread never inherits ownership | tested | `test_file_lock_registry.py::test_a_second_thread_is_not_treated_as_the_owner` PASSED |
  | 25e | A release by a non-owner does not free the owner's lock | tested | `test_file_lock_registry.py::test_release_by_a_non_owner_is_a_noop` PASSED |
  | 25f | A forked child does not inherit ownership (pid guard) | tested | `test_file_lock_registry.py::test_a_forked_child_does_not_inherit_ownership` PASSED — simulated via the module reference so it runs on Windows, where `os.fork` does not exist |
  | 25g | A failed acquisition leaves the instance able to acquire AND still excluding others | tested | `test_file_lock.py::test_instance_is_clean_after_a_timeout` PASSED — strengthened from an attribute check to a behavioural one after Stage 2 |
  | 29 | A forked child does not RELEASE the parent's lock | tested | `test_file_lock_registry.py::test_a_forked_child_does_not_release_the_parents_lock` PASSED — the acquire-side guard alone left this open (external code review, high) |
  | 30 | A refused `stat` still lets the write land, end-to-end | tested | `test_durable_publish.py::test_write_survives_an_unstattable_destination` PASSED |
  | 31 | The runner fixture carries BOTH new siblings | tested | `test_f0_cli_diff_coverage_e2e.py` + `test_f0_diff_coverage_e2e.py` — 6 passed with `durable_publish` **and** `file_lock_registry` listed |
  | 26 | The loader fallback still loads a lib module past a shadowing `lib` | tested | `test_shared_lib_loader_fallback.py::test_fallback_loads_a_lib_module_past_a_shadowing_lib` PASSED (4 params) — added after the doubt review; `probe_loader.py` shows it failing against the pre-fix loader |
  | 26b | A sibling import inside a loaded lib module resolves | tested | `…::test_a_sibling_import_resolves_inside_the_private_package` PASSED — the exact breakage (`file_lock`→`file_lock_registry`, `atomic_write`→`durable_publish`) |
  | 26c | The loader never puts `shared/scripts/lib` on `sys.path` | tested | `…::test_the_loader_never_puts_lib_on_sys_path` PASSED — the shortcut fix would have relocated the collision (`config.py`/`state.py` live there) |
  | 26d | An unknown module still raises `ImportError` | tested | `…::test_an_unknown_module_still_raises_importerror` PASSED |
  | 27 | Windows: contention is retried, a real fault propagates immediately | tested | `test_file_lock_bounded.py::test_a_real_fault_propagates_instead_of_being_polled` PASSED — measured signatures (`probe_msvcrt.py`): contention `PermissionError`/EACCES, fault plain `OSError`/EBADF |
  | 28 | `os.name == "nt"` alone disables the mode carry | tested | `test_durable_publish.py::test_windows_never_carries_even_if_fchmod_appears` PASSED — stops the carry self-arming if a future CPython grows `os.fchmod` on Windows |
  | 25 | Real POSIX `chmod`/`fchmod` semantics on a live filesystem | untestable | `covered-by-existing-test` is NOT claimed here — rows 1-2 cover it but only execute on the ubuntu CI runner. Locally this host cannot execute it at all; row 3 pins the selection logic everywhere so the untested part is narrowed to the syscall itself, not the decision |

  **0 untested-testable** — but only after Stage 1. The first draft claimed it
  while AC-3 had no end-to-end test at all: row 4 pointed at a test that asserts
  the *negation* of AC-3 (the write failing), under a name and docstring that
  said "AC-3". That is precisely the failure this ledger exists to catch, and it
  took a reviewer reading the test body to catch it — a row saying `tested` with
  a real, passing, correctly-named test is not the same as a row whose test
  proves the claim. Row 4 now names a test that drives a refused `fchmod`
  through `durable_atomic_write`; row 4b is what the old test really pinned.

  Row 25 is the only non-`tested` disposition and it is an honest platform limit
  of the dev host, not a deferral: those rows run green on the Linux CI leg,
  which is where the defect lives.

- **Confidence-pattern check:**
  - **Asymptote (depth).** The pattern fired repeatedly, and every time it was a
    *reviewer* who broke the asymptote rather than another pass of my own
    re-reading. The plan asserted finding 10's symptom as fact and the first
    probe falsified it. Stage 1 found the ledger claiming "0 untested-testable"
    while AC-3's named test asserted the *negation* of AC-3. Stage 2 found the
    registry re-implementing an in-repo precedent without its safety properties.
    Stage 3 found an import-shape regression that would have silently lost triage
    findings and that no test root I had run could see. And the external cascade
    then found **three defects introduced by the Stage-3 remediation itself** —
    including a fork hole in code two reviewers had already passed.
    The honest reading: "are you confident?" was answerable *yes* at four
    separate points in this run, and was wrong at all four. What moved it was
    always a probe or an adversary, never more confidence.
  - **Coverage (breadth).** 31 behaviour rows, 30 `tested`, 0 untested-testable.
    12,756 tests across all eight pytest roots.
  - **Integration composition.** `cross_component` does not fire — neither
    module matches `CROSS_COMPONENT_FILE_PATTERNS`, verified by reading the
    pattern tuple, and the F11 verifier recomputes it from the diff
    independently. No `category:"integration"` behavior is owed. The nearest
    equivalent was run anyway: the four consuming test roots were executed in
    full rather than only the four touched files.

## Verification (medium+)

- **Surface:** cli
- **Runner command:**
  `uv run pytest shared/tests/test_atomic_write.py shared/tests/test_atomic_write_windows_retry.py shared/tests/test_atomic_write_windows_read_retry.py shared/tests/test_durable_publish.py shared/tests/test_durable_publish_winerrors.py shared/tests/test_file_lock.py shared/tests/test_file_lock_bounded.py shared/tests/test_file_lock_registry.py -q`
- **Evidence path:** `.shipwright/runs/iterate-2026-08-06-write-lock-primitives/surface_verification.json`
- **Justification:** n/a (surface is not `none`)

The surface is a CLI/pytest invocation because both primitives are libraries with
no startable UI or HTTP surface. All eight files sit under the single
`shared/tests` pytest root, so the run does not violate the one-root rule.

The list grew from four files to eight during the run: two test files were split
when they outgrew the 300-line limit (`test_durable_publish` → `_winerrors`,
`test_file_lock` → `_bounded`) and two are new (`_registry`, and the read-retry
sibling pulled in for completeness). The loader regression test
(`shared/scripts/tests/test_shared_lib_loader_fallback.py`) is deliberately NOT
here — it lives under a *different* pytest root, and composing roots in one
process is a hard error in this repo (ADR-044). It runs in F0's canonical suite,
which invokes each root separately.
