# Mini-Plan: write-lock-primitives

- **Run ID:** iterate-2026-08-06-write-lock-primitives
- **Spec:** `.shipwright/planning/iterate/2026-08-06-write-lock-primitives.md`
- **Type:** bug · **Complexity:** medium

## 1. Files to create / modify

| File | Change | Why |
|---|---|---|
| `shared/scripts/lib/durable_publish.py` | **new** | Holds the winerror set (finding 10 edits it) and the new POSIX mode carrier (finding 20 adds it). Exists because `atomic_write.py` is at 299/300 lines. |
| `shared/scripts/lib/atomic_write.py` | edit | Import the leaf; call the mode carrier before the fsync; keep `_SHARING_VIOLATION_WINERRORS` as an alias. Lands at **exactly 300** lines (299 → 300; the winerror block moving out pays for the import). `bloat_baseline.scan` fires above 300, so no new crossing is created. |
| `shared/scripts/lib/file_lock.py` | edit | `FileLock` gains a bounded wait and same-thread reentrancy; the module's two former poll loops collapse into one. |
| `shared/scripts/lib/file_lock_registry.py` | **new** (added at Stage 2) | The process-scoped "what do we hold" registry, mirroring `_host_resource_locking`'s shape. Split out so the pid guard and the non-raising key could be added at all — `file_lock.py` was at the ceiling. |
| `shared/scripts/tools/setup_iterate_worktree.py` · `shared/scripts/lib/sweep_outbox.py` · `shared/scripts/lib/reconcile_triage.py` | edit (comment only) | Record that `LockTimeout` now propagates out of the sweep — the "never raises" contract was silently falsified by the bound. No behaviour change; all three stay at their original line counts. |
| `shared/tests/test_file_lock_registry.py` | **new** | Registry invariants: cwd-independent key, non-raising key, per-thread ownership, non-owner release, fork guard. |
| `shared/tests/test_durable_publish.py` | **new** | Unit tests for the leaf. |
| `shared/tests/test_atomic_write.py` | edit | AC-1/2/3 — mode preservation through the real primitive. |
| `shared/tests/test_atomic_write_windows_retry.py` | ~~edit~~ **unmodified** | Predicted an edit here for AC-4; the file was at 280/300 lines, so the winerror-33 coverage went into `test_durable_publish.py` beside the set it exercises instead. Its existing "unlisted code is re-raised" test already pins the other half of the filter and passes unchanged (ledger row 11). Row kept rather than deleted so the prediction and the outcome stay visible. |
| `shared/tests/test_file_lock.py` | edit | AC-5/6/7/8 — timeout, reentrancy, opt-out, no regressions. |

## 2. Work breakdown (sequential)

1. **Leaf module `durable_publish.py`.**
   `SHARING_VIOLATION_WINERRORS = frozenset({5, 32, 33})` with the measured
   rationale for each code, and `carry_destination_mode(fd, dest)` — which
   takes the **open descriptor**, not the temp path, and uses `os.fchmod`
   (external review, high — see §7.1). Returns whether the mode was carried,
   and keeps a `mode_carry_failures()` counter in the module's own idiom
   (§7.9).
   *Test:* `test_durable_publish.py` — carries an existing mode, leaves a
   missing destination alone, swallows a `fchmod`/`stat` `OSError` and counts
   it, no-ops where `os.fchmod` is absent.
2. **Wire it into `atomic_write.py`.** Sibling-import preamble (the pattern
   `bloat_baseline.py` already uses in this directory); call
   `carry_destination_mode(fh.fileno(), path)` **while the descriptor is still
   open and before the existing `os.fsync`**, so the mode change is covered by
   the same fsync that makes the bytes durable; alias the winerror name.
   *Test:* AC-1/2/3 via `durable_atomic_write` end-to-end; AC-4 via
   `_retry_past_sharing_violations` with the Windows branch forced; plus the
   alias-identity drift test (§7.10).
3. **`FileLock` bounded wait.** `FILE_LOCK_DEFAULT_TIMEOUT_SECONDS = 600.0`;
   constructor kwarg `timeout_seconds` (`None` = historical unbounded, `0` =
   one non-blocking attempt), **validated** to `None` or a finite non-negative
   number or `ValueError` (§7.3); deadline on `time.monotonic()`. POSIX
   switches from `flock(LOCK_EX)` to `LOCK_EX | LOCK_NB` + a shared backoff
   poll (1 ms → 50 ms, clamped to the remaining budget) that both branches
   use (§7.7). Expiry raises the module's existing `LockTimeout` naming the
   path and the wait. Any unsuccessful `__enter__` closes the handle and
   clears instance state (§7.2).
   *Test:* AC-5 (other thread holds → `LockTimeout` inside the budget),
   AC-7 (`None` still blocks, `0` fails fast), AC-8 (mutual exclusion + parent
   mkdir intact), plus no-descriptor-leak after a timeout.
4. **`FileLock` same-thread reentrancy.** Process-global registry keyed on the
   normalised resolved lock path → (owner thread ident, depth, handle),
   guarded by a `threading.Lock`. The registry check happens **first**, before
   `mkdir` and before `open(path, "w")`, so a nested entry never re-truncates
   the sidecar (§7.5). Nested `__enter__` from the owning thread increments
   depth and returns without touching the OS lock or the handle; `__exit__`
   releases only at depth 0, and **the OS-level release and the registry
   removal both happen under the registry guard** so an acquirer never observes
   a released lock with a stale entry (§7.8). Each instance tracks how many
   registry increments *it* made, so `__exit__` after a failed `__enter__`, a
   double `__exit__`, and a re-used instance are all safe (§7.2).
   *Test:* AC-6 (nested `with` across two instances enters immediately; a
   second thread is still excluded while the inner block runs; the lock is
   released only after the outermost exit); exception inside the inner and the
   outer block still unwinds correctly.
5. **Re-run the full affected surface** and record the F0.5 evidence.

## 3. Component hierarchy

n/a — no UI.

## 4. Data model changes

None. No schema, no serialized format, no migration.

## 5. Test strategy

- **Deterministic on both platforms.** The Windows-retry tests force the branch
  via `aw._is_windows` (never `os.name` — see that function's docstring), so
  AC-4 runs on the Linux CI runner too.
- **POSIX-only assertions** (AC-1/2, real `chmod` semantics) are guarded
  `skipif(os.name == "nt")`. CI is `ubuntu-latest`, so they **run in CI** and
  skip only on the Windows dev host — the silent-skip CI-discipline rule's
  concern (a skip hiding a gap *in CI*) does not arise, and the guard is a
  platform predicate, not a missing-binary dodge. The mode carrier's Windows
  no-op is asserted separately so neither platform has an untested branch.
- **No test may hang.** The self-deadlock repro runs the nested acquisition on
  a daemon thread and asserts on `join(timeout=…)`, so a regression fails the
  suite instead of wedging it.
- **E2E:** not applicable — no browser surface. F0.5 runs the four affected
  test files as the `cli` surface.

## 6. Alternative approach (considered, rejected)

**Extract the Windows retry engine out of `atomic_write.py` and make room that
way** — move `_is_windows`, `_retry_past_sharing_violations`, the counter and
the constants into a sibling, leaving `atomic_write.py` around 210 lines.

*Rejected.* `aw._is_windows` is monkeypatched in 12 places across four test
files and `_fsync_parent_dir` is imported by `iterate_test_results.py`, so the
move ripples into files this fix has no business touching — and the operator's
split of `trg-79102ee3` explicitly separates pure moves from data-loss fixes
(card `trg-de99fdcb`) so review is not diluted. The chosen leaf relocates only
the winerror set, which finding 10 is editing anyway; nothing moves that this
diff would not otherwise modify.

**Second alternative: let `atomic_write.py` cross 300 lines and record it.**
Rejected too — a new crossing is advisory rather than blocking, so it would
have shipped quietly as a Group H finding for someone else to clean up. The
limit did its job here; a genuinely separable leaf is the answer it was asking
for.

## 7. External LLM plan review — findings and disposition

Run at Branch A (`check-external-review-keys.py` → `available`).
Verdicts: **openai = revise**, **deepseek = approve** (agree within one step;
no contradiction). All ten findings are addressed below; none is deferred.

### 7.1 (openai, HIGH) — the mode change must be covered by the fsync — ADOPTED

The plan said "chmod the temp before the rename", which would have applied the
mode *after* the temp file's `fsync` and left the metadata change resting on a
parent-directory fsync that does not cover it. For a primitive whose entire
reason to exist is durability ordering, that is the wrong shape. The carrier
now takes the **open descriptor** and uses `os.fchmod` immediately before the
existing `fh.flush()` / `os.fsync(fh.fileno())`, so one fsync covers bytes and
mode together and no second fsync is needed. This also removes the leaf's need
for a platform predicate: it keys on `hasattr(os, "fchmod")`, which is exactly
the capability being used.

### 7.2 (openai, MEDIUM) — explicit instance state + failure cleanup — ADOPTED

`FileLock` gets an instance-level count of the registry increments *it* made.
Ownership is never inferred from the path. Every unsuccessful `__enter__` path
closes the handle it opened and leaves the instance un-entered, so a timeout
cannot leak a descriptor or leave an instance looking acquired. `__exit__`
after a failed `__enter__`, a double `__exit__` and a re-used instance are all
no-ops rather than acting on a stale handle — a strict superset of the
existing `self._fp = None` reset. Tests cover timeout cleanup and an exception
raised inside both the inner and the outer nested block.

### 7.3 (openai, MEDIUM) — validate `timeout_seconds`, use a monotonic deadline — ADOPTED

`NaN` is the sharp edge: every deadline comparison against it is `False`, so it
would have recreated an unbounded wait without anyone passing `None`. The
constructor now accepts `None` or a finite non-negative number and raises
`ValueError` otherwise (`math.isfinite` rejects both `NaN` and `inf`). The
deadline is computed from `time.monotonic()`, never wall-clock, so a clock
adjustment cannot shorten or extend a wait. `timeout_seconds=0` is defined and
tested as exactly one non-blocking attempt.

### 7.4 (openai, MEDIUM) — justify 600 s against the *complete* critical section — ADOPTED, and the plan's own justification was wrong

The reviewer is right that the original justification bounded one subprocess
rather than the whole hold. Inventory of every `FileLock` call site:

| Critical section | git subprocesses under the lock | Bounded worst case |
|---|---|---|
| `sweep_outbox.sweep_outbox_to_branch` (worktree setup step 5) | `show` + `rev-parse` + `diff --cached` + `checkout` via `sweep_drift` (4 × 15 s) + `add` + `diff --cached` (2 × 15 s) + `commit` (120 s) | **~225 s** |
| `reconcile_triage.reconcile` | ~4 × `status --porcelain` / `show HEAD` (15 s) + `commit` (120 s) | ~180 s |
| `record_event` (×3), `iterate_timings`, `triage_gc` | none — pure file work | sub-second |

The original "5 × 120 s" reasoning was simply wrong: only the **commit** in
each section is given `HOOK_GIT_TIMEOUT` (120 s); every other call uses
`DEFAULT_GIT_TIMEOUT` (15 s). The true bound is ~225 s, so 600 s clears the
longest *fully pathological* hold by ~2.7× — no healthy holder (sub-second)
and no all-subprocesses-timing-out holder can trip it. The number stays, but it
now rests on the inventory the reviewer asked for. The alternative the reviewer
offered — a bespoke timeout on the sweep call site — was not taken, because a
default that already clears the worst bounded case makes per-site tuning
unnecessary and would have spread the diff across call sites for no gain.

### 7.5 (openai, LOW) — check the registry before `mkdir` / `open` — ADOPTED

Ordering corrected: normalise the key, check same-thread ownership, and only a
non-reentrant acquisition creates the parent directory, opens the sidecar
(`"w"`, which truncates) and attempts the OS lock. Otherwise a reentrant entry
would re-truncate the lock file and could fail on filesystem setup while
already holding the lock. The original path is kept verbatim for diagnostics;
the canonical key is used only for registry identity.

### 7.6 (openai, MEDIUM) — the anti-hang test must not contaminate the suite — ADOPTED

A regression would otherwise leave a daemon thread parked on the new 600 s
default, holding the outer lock until process exit and poisoning later tests.
Every contention test uses pytest's per-test `tmp_path`, an explicit short
`timeout_seconds`, `threading.Event` synchronisation, release in `finally`, and
`join()` before teardown. Elapsed-time assertions use a tolerance band, never
an exact sleep.

### 7.7 (deepseek, MEDIUM) — POSIX poll needs a backoff — ADOPTED

Both branches share one backoff helper: first retry at 1 ms (preserving the
current Windows latency), doubling to a 50 ms cap, each sleep clamped to the
budget actually remaining so the last attempt lands at the deadline rather than
past it — the same discipline `atomic_write._retry_past_sharing_violations`
already documents. Capped at 50 ms rather than the suggested 1 s: these locks
guard sub-second appends, and a 1 s cap would add up to a second of latency to
the common uncontended-after-a-blink case.

### 7.8 (deepseek, MEDIUM) — release and de-register atomically — ADOPTED

The registry guard is held across **both** the OS-level unlock and the entry
removal, so an acquirer can never observe a released OS lock while a stale
registry entry still names an owner. The guard is held across a syscall, which
is deliberate and cheap (microseconds) and is what makes the ownership check
sound.

### 7.9 (deepseek, LOW) — a swallowed `fchmod` failure hides a posture change — ADOPTED, in the module's own idiom

A silently narrowed mode is a security-posture change, so it must not be
invisible. Not solved with `warnings.warn` — globally suppressible, and this
module already argued (retry counter, `trg-0a294ef3`) that a warning has no
consumer while a counter does. `carry_destination_mode` reports whether it
carried the mode and the leaf exposes `mode_carry_failures()` /
`reset_mode_carry_failures()`, mirroring `sharing_violation_retries()` exactly.
The write still never fails on a `chmod` error (AC-3).

### 7.10 (deepseek, LOW) — pin the alias to the leaf — ADOPTED

`test_durable_publish.py` asserts
`atomic_write._SHARING_VIOLATION_WINERRORS is durable_publish.SHARING_VIOLATION_WINERRORS`,
so a later edit that rebinds the alias instead of editing the leaf fails a test
rather than silently forking the source of truth.
