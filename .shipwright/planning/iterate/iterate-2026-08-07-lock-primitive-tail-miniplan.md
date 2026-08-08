# Mini-Plan: lock-primitive-tail

- **Run ID:** iterate-2026-08-07-lock-primitive-tail
- **Bundles:** trg-6d8fbc10 (P2.19i) — trg-db1de213 + trg-2e961fee, both fell
  out of iterate-2026-08-06-write-lock-primitives (P2.19d, trg-dc013d82)
- **Type:** bug · **Complexity:** small (auto-classified; treated with
  elevated review rigor at the operator's explicit request — internal Opus
  plan review + external plan review + review cascade, all normally reserved
  for medium+)
- **Blocker status:** P2.19d (trg-dc013d82) is **merged** (PR #580, dismissed
  in triage "Implemented PR #580") — the block this card named is resolved.

## 0. Corrected assumption, carried forward (not restated)

P2.19d finding 10 originally assumed a byte-range lock on the destination
would surface Windows error code 33. Two measurements (once during
iterate-2026-07-27-run-unit-parallel-race, once during P2.19d itself) both
show that assumption is **false**: it surfaces **5**, because holding a byte
range requires holding the file open, and the open handle alone already
yields 5. `durable_publish.py`'s `SHARING_VIOLATION_WINERRORS` docstring
already carries this corrected measurement (P2.19d wrote it there) — this
run does not restate the false "33" claim anywhere, and does not re-litigate
it. What P2.19d's own probe surfaced instead, and deliberately deferred, is
finding (1) below: a **different** failure shape entirely (no code at all).

## 1. Files to create / modify

| File | Change | Why |
|---|---|---|
| `shared/scripts/lib/atomic_write.py` | edit | `_retry_past_sharing_violations` gains a `retry_none_winerror` kwarg (default `False`, write path unaffected); `durable_read_text`/`durable_read_bytes` opt in. |
| `shared/scripts/lib/durable_publish.py` | edit (docstring only) | The `SHARING_VIOLATION_WINERRORS` paragraph said the None-winerror read gap was "filed as its own card" — replaced with where the fix actually lives, now that this run is that card. |
| `plugins/shipwright-run/scripts/lib/phase_task_lifecycle.py` | edit | `_PhaseTasksLock` becomes a thin subclass of `lib.file_lock.FileLock` instead of a third literal copy of the wait/lock loop; own `sys.path` insert added (mirrors `run_config_store.py`, not relying on its import order — ADR-045). `time` import dropped (only user was the old spin loop). |
| `shared/tests/test_atomic_write_read_winerror_none.py` | **new** | Read-side retry-then-succeed, retry-then-raise, write-side non-retry (asymmetry guard), and a real `msvcrt` byte-range-lock fidelity test. |
| `plugins/shipwright-run/tests/test_phase_tasks_lock.py` | **new** | Delegation drift guard (`issubclass`), lock-path identity, bounded-not-unbounded, same-thread reentrancy end-to-end. |

Both new test files are separate rather than appended to existing siblings:
`test_atomic_write_windows_retry.py` is at 280/300 lines already, and
`test_phase_task_lifecycle.py` is well past 300 — appending to either would
ratchet an existing bloat-baseline entry.

**Two already-tracked files still cross their own baseline entries:**
`phase_task_lifecycle.py` (`current: 660` → ~693, from the `_PhaseTasksLock`
delegation, the `_guard_lock_timeout` decorator, and §8's caller-check fix)
and `test_single_session_loop.py` (`current: 306` → ~346, from §9.2's new
regression test). Neither has a split-the-file option that wouldn't
fragment an already-cohesive module/suite for a double-digit-line net
change. The remediation is the project's own sanctioned **last-step
baseline refresh** (`CLAUDE.md` "Baseline refresh LAST" / F-phase
finalization) for both entries — run immediately before the F6 commit,
after every other edit in this diff is final, so the refreshed `current`
values reflect the actual shipped line counts and nothing after them can
silently ratchet further unnoticed.

## 2. Work breakdown (sequential)

1. **Reproduce finding (1) for real** before touching code (Iron Law). A
   Windows probe holds a byte-range lock via `msvcrt.locking` on one handle
   and calls `durable_read_text` from the same process: confirmed
   `PermissionError(winerror=None)` raised in 0.000s (not retried) against
   today's code.
2. **Fix the retry predicate.** Read-only opt-in (`retry_none_winerror`) so
   the write path's semantics are untouched — a `None` winerror on
   `os.replace` is a different, non-transient failure (temp-file mode/perm
   errors), and retrying it would trade a loud failure for a silent stall.
   Re-ran the same probe: now retries for the full read budget before
   raising.
3. **Delegate `_PhaseTasksLock`.** Confirmed by grep that no caller nests
   this lock inside itself today (matches `trg-2e961fee`'s own claim:
   reentrancy is a guardrail, not an active fix), so the behavior change is
   pure hardening. Same lock file name as `run_config_store.run_config_lock`
   and `append_phase_history`'s `file_lock` (`shipwright_run_config.json.lock`)
   — verified the OS-level primitives are identical (`fcntl.flock` /
   `msvcrt.locking` on byte 0), so the three continue to mutually exclude
   regardless of which wrapper acquired the lock.
4. **Regression tests + full affected suites.** New tests above; ran
   `shared/tests/` and `plugins/shipwright-run/tests/` in full (the latter
   needed `uv sync --extra dev` for `pytest-mock` — a fresh-worktree gap, not
   a code issue).

## 3. Component hierarchy

n/a — no UI.

## 4. Data model changes

None. No schema, no serialized format, no migration.

## 5. Test strategy

- **Deterministic stub tests** for the retry-predicate shape (mirrors the
  existing `test_atomic_write_windows_retry*.py` style: patch
  `aw._is_windows`, never `os.name`).
- **One real-OS fidelity test** (`skipif` off Windows) using genuine
  `msvcrt` byte-range locking, so the fix is proven against the actual OS
  behavior it was measured against, not only an injected stub.
- **Lock delegation** is proven by three narrow tests (subclass, lock-path
  identity, bounded-not-unbounded) plus one end-to-end same-thread nested
  acquisition — the underlying bounded/reentrant mechanics are NOT
  re-tested here; that coverage already exists exhaustively in
  `shared/tests/test_file_lock_bounded.py`, and duplicating it would be the
  fourth copy this fix exists to remove.
- **No test may hang**: the reentrancy test runs on the same thread with no
  timeout-dependent wait, so a regression fails fast rather than wedging
  the suite.

## 6. Alternative approaches (considered, rejected)

**Fix the read-side retry gap by widening `_SHARING_VIOLATION_WINERRORS` to
include `None`.** Rejected: the set is shared by both the read and write
predicates today, and a `None` winerror on the WRITE path is a different,
non-transient failure (see `durable_publish.carry_destination_mode`'s own
reasoning about a permanently-unwritable destination). Widening the shared
set would make the write path retry a real failure for the full budget
before re-raising it — trading a loud failure for a silent stall on the
side where that trade is explicitly rejected elsewhere in this same module.
An opt-in kwarg keeps the asymmetry explicit and testable in both
directions (see `test_write_side_does_not_retry_a_none_winerror`).

**Give `_PhaseTasksLock` its own bound/reentrancy instead of delegating.**
Rejected on the same grounds `trg-2e961fee` names: it would be the fourth
copy of the same wait-loop mechanics discovered as three redundant copies,
this time knowingly instead of by drift. Delegating to `lib.file_lock.
FileLock` replaces ~25 lines of hand-rolled locking with an ~24-line
subclass (docstring included) and inherits every future fix to the shared
primitive for free — near line-neutral on the class itself; the net growth
in the file comes from the `LockTimeout`-contract fix in §7.

**A narrower `_SHARING_VIOLATION_WINERRORS`-only fix, skipping the `errno`
check.** Considered during plan review and rejected: bare `winerror is None`
would also retry an EPERM-shaped `PermissionError` that happens to carry no
`winerror` — a shape never measured on this path. Requiring
`errno.EACCES` too keeps the opt-in scoped to exactly what was measured (see
§7.7).

## 7. Plan review — findings and disposition

Internal Opus plan review (`shipwright-plan:opus-plan-reviewer`, model=opus)
ran against this plan and the (at-the-time) implemented diff. 11 findings, 4
medium / 7 low. All addressed; none deferred.

### 7.1 (MEDIUM) — reentrancy on a read-modify-write lock — ADOPTED (documented)

Correct: the old copy's unbounded self-deadlock on nesting was, perversely,
also a loud guard against a future nested call silently clobbering the
outer holder's in-memory config. No caller nests today (verified by grep),
so this is not an active defect — but it is a trap for a future refactor.
`_PhaseTasksLock`'s docstring now states the constraint explicitly: no
lock-taking public function may be called from inside another one's `with`
block, and names `mark_phase_failed` / `complete_phase_task` as the pair
that must stay correctly ordered.

### 7.2 (MEDIUM) — the inherited 600s bound was sized for a different lock — ADOPTED

Correct, and the fix is a one-line change with real consequence: passed
`run_config_store.DEFAULT_LOCK_TIMEOUT_SECONDS` (30s) explicitly instead of
inheriting `FileLock`'s own 600s default, which was derived for the triage
sweep's ~225s worst case, not this lock's fast RMW. Without this, a stuck
holder on this lock would wait 10 minutes for the diagnostic this whole run
exists to produce, while its two siblings on the identical lock file give
up in 5s/30s. `test_is_bounded_using_the_run_config_lock_sibling_value`
pins 30s with the reasoning, not the inherited number.

### 7.3 (MEDIUM) — `LockTimeout` now escapes 6 functions documented to always return a dict — ADOPTED

Correct and the most consequential finding: `orchestrator_pkg/router.py`'s
dispatcher and (found while fixing this) three MORE direct callers
(`single_session_apply.py`, `single_session_loop.py`,
`single_session_recovery.py`) call these functions with no try/except.
Fixed with a `_guard_lock_timeout` decorator applied to all six
lock-taking public functions, converting `LockTimeout` into the module's
`ok: False` / `reason: "lock_timeout"` shape at the source rather than at
each of four call sites (cheaper, and correct for callers not yet written).
`test_a_lock_timeout_becomes_ok_false_not_a_raised_exception` pins it.

### 7.4 (MEDIUM) — cross-implementation exclusion tested in only one direction — ADOPTED (measured)

Correct that the untested direction (another holder via the sibling's
non-truncating `"a+"` open, THEN this class's truncating `"w"` open) was the
riskier one to leave unmeasured — exactly the kind of Windows claim this
whole card exists to insist gets measured, not assumed. Measured directly
before writing the test: the truncating open does NOT hard-crash; it waits
and raises `LockTimeout` cleanly, same as the already-tested direction.
`test_a_holder_via_the_sibling_a_plus_lock_is_waited_out_not_crashed_into`
pins the measurement.

### 7.5 (LOW) — plugin-cache sync step missing from the plan — ACKNOWLEDGED, deferred to F11

Correct that `plugins/shipwright-run/scripts/lib/` changes need
`scripts/update-marketplace.sh` + `check_plugin_cache_sync.py --strict`
after push. This is standard finalization procedure for every iterate
touching plugin-side files (CLAUDE.md), not specific to this plan — done at
delivery, not re-stated here.

### 7.6 (LOW) — stale docstrings naming only two consumers — ADOPTED

`file_lock.py`'s module docstring and `run_config_store.py`'s "coordination
by path, not shared code" paragraph both named only the original two
`FileLock` consumers. Both updated to name `_PhaseTasksLock` as the third
(`file_lock.py` edited to stay at exactly 300 lines — no new bloat
crossing, matching this repo's established practice of trimming rather
than raising a cap).

### 7.7 (LOW) — retry opt-in broader than the measured shape — ADOPTED

Correct: `winerror is None` alone would also retry an EPERM-shaped
`PermissionError`, a shape never measured on this path. Tightened to also
require `exc.errno == errno.EACCES`, matching exactly what was measured.
`test_read_does_not_retry_a_none_winerror_with_a_different_errno` pins it.

### 7.8 (LOW) — write-asymmetry justification stated as fact, not reasoning — ADOPTED

Reworded the docstring from an assertion ("is a different, non-transient
failure") to the honest form used elsewhere in this module ("no measured
transient failure... produces a None winerror on this path"), matching
`durable_publish`'s own labelling discipline (its "33 is defence in depth,
not a measured fix" precedent).

### 7.9 (LOW) — `sharing_violation_retries()` counter now conflates two causes — ADOPTED (documented)

A second counter was considered and rejected as over-engineering for a
process-local diagnostic nobody currently splits by cause; the docstring
now says explicitly that byte-range-lock read retries fold into the same
tally as sharing-violation retries, so a future reader is not misled.

### 7.10 (LOW) — plan-text line-count arithmetic was wrong — ADOPTED (this section)

Correct — "64 replacing 35" was a net addition, not the "net deletion" the
prose claimed. Corrected above (§6).

### 7.11 (LOW) — the real-OS fidelity test is timing-dependent and CI-invisible — ADOPTED

Widened `READ_RETRY_BUDGET_SECONDS` to 10s for that one test (was the
module's 2s default racing a 0.15s release) and added a docstring note
that it is a local-only fidelity check, not the suite's regression gate —
the deterministic stub tests are.

## 8. External LLM plan review — findings and disposition

Run via `external_review.py --mode iterate` (GPT + DeepSeek, per this run's
explicit instruction), recorded verbatim in
`.shipwright/planning/iterate/iterate-2026-08-07-lock-primitive-tail/reviews.json`
(`plan` row). Verdicts: **openai = revise**, **deepseek = approve** — agree
within one step, no contradiction. **6 findings** (this section previously
mis-transcribed 8, three of them not present in the recorded evidence; the
first spec-reviewer pass on this diff caught the drift — see §9). All 6
below map 1:1 to `reviews.json:findings[0..5]`.

### 8.1 (deepseek, MEDIUM) — caller must inspect the `ok: False` return, not assume success — RESOLVED

Real gap, not a theoretical one: three of the four real `freeze_splits`/lock-
taking call sites already checked `.get("ok")` (`router.py`,
`single_session_recovery.py`, `single_session_loop.py`), but
`single_session_apply.py:157-161` called `lc.freeze_splits(project_root)`
inside a bare `try/except Exception` and never read the returned dict — so
a `lock_timeout` there (now a *returned* `ok: False`, not a raised
exception) would have been silently swallowed and the design phase would
have completed with `splits_frozen` never written. Fixed by checking
`freeze_result.get("ok")` and returning `{"ok": False, "reason":
"freeze_splits_failed", ...}` when it's false, matching the other three
call sites' pattern. New regression test:
`test_apply_design_surfaces_a_freeze_splits_failure_instead_of_completing`
(`plugins/shipwright-run/tests/test_single_session_loop.py`).

### 8.2 (deepseek, LOW) — confirm all six decorated functions already return a dict on success — VERIFIED

Audited every `return` statement inside `claim_phase_task`,
`mark_phase_failed`, `complete_phase_task`, `recover_phase_task`,
`freeze_splits`, `plan_next_phase`: every path returns either `_ok(...)`,
`_fail(...)`, or a value obtained from those (e.g. `_check_owner_version`'s
`Optional[dict]`) — no non-dict return exists. No code change; the module's
`_ok`/`_fail` helper convention was already load-bearing here.

### 8.3 (openai, MEDIUM) — plugin cache sync not an executable step — ACKNOWLEDGED, deferred to F11

Same finding as the internal review's §7.5 — standard finalization
procedure for this run, not a plan gap. Executed at delivery.

### 8.4 (openai, MEDIUM) — add a parameterized test covering all six decorated functions — IMPLEMENTED

The originally-shipped regression test only exercised `freeze_splits`; a
missed or malformed `@_guard_lock_timeout` on any of the other five would
have passed unnoticed. Added
`test_every_guarded_function_converts_a_lock_timeout_to_ok_false`,
parametrized over all six with placeholder args (the timeout fires during
lock *acquisition*, before any body logic reads `phase_tasks[]`, so the
argument values are never inspected — only their shape needs to satisfy
each signature). Subsumes and replaces the single-function test.

### 8.5 (openai, LOW) — implement the decorator with `functools.wraps` — IMPLEMENTED

`_guard_lock_timeout` now uses `@wraps(fn)`, so all six public functions
keep their real `__name__`/`__doc__`/annotations instead of the wrapper's.

### 8.6 (openai, LOW) — no new security boundary; the `errno.EACCES` + `winerror is None` retry trade-off is bounded and narrow — CONFIRMED, no action

Agrees with the approach as shipped (Windows-only gating, write-path
non-retry test kept as a regression guard).

## 9. Stage 1 spec-review (opus) — findings and disposition

`shipwright-build:spec-reviewer`, model=opus, run against this plan and the
diff (per the run's explicit review-cascade instruction). **Verdict: REJECT**
— 3 findings, all genuine, all fixed below (recorded in `reviews.json`'s
`spec` row as the cascade proceeds).

### 9.1 (unfaithful) — §8's disposition table didn't match the recorded review evidence

Caught the exact drift §8 above is now rewritten to fix: this section
previously claimed 8 external findings (numbered 8.1–8.8); the recorded
evidence (`reviews.json`) has 6. Three of the eight numbered items here had
no counterpart in the evidence at all, and — worse — one of them
(`_guard_lock_timeout` "could catch an unrelated LockTimeout") was cited
inside *shipped source* as `(external plan review, openai)`, misattributing
a self-authored design note as reviewer evidence. Meanwhile three *real*
recorded findings (the caller-check gap, `functools.wraps`, the six-function
parameterized test) were silently undispositioned. Fixed: §8 rewritten to
match `reviews.json:findings[0..5]` 1:1; the misattributed docstring
citation in `phase_task_lifecycle.py` corrected to drop the false review
attribution.

### 9.2 (unfaithful) — the caller-check gap §8.1 named was real code, not just documentation drift

`single_session_apply.py`'s `freeze_splits` call site discarded the return
value — the exact silent-swallow the deepseek MEDIUM finding (§8.1) warned
about, and the one call site (of four) that didn't already check `.get("ok")`
before this run. Fixed in `single_session_apply.py`; regression test added
(`test_apply_design_surfaces_a_freeze_splits_failure_instead_of_completing`).
See §8.1 for the full account.

### 9.3 (missing) — `phase_task_lifecycle.py`'s bloat-baseline crossing had no stated remediation

§6 acknowledged the file's line growth but never named what happens about
it. Fixed: §1 now states the remediation explicitly (baseline refresh as
the sanctioned last pre-commit step, not silently ignored) — see §1.

## 10. Stage 3 doubt-review (opus) — findings and disposition

`shipwright-build:doubt-reviewer`, model=opus, fresh context, biased to
DISPROVE — triggered because this diff touches concurrency/locking
primitives. **Advisory, not a hard gate**; every objection addressed below.
Attempted and failed to disprove: nested lock-taking pairs among the six
functions, a POSIX regression from the retry-predicate change, a vacuous
parametrized guard test, and any interaction between the two bundled
fixes — all four cleared on inspection, no action.

### 10.1 (MEDIUM) — `lock_timeout` was contractually indistinguishable from a terminal failure — FIXED

Every other `ok: False` reason this module returns is a determination
about state (retrying is pointless); a lock timeout is the opposite
(retrying is the correct response), and nothing in the returned dict said
so. Added `retryable=True` to `_guard_lock_timeout`'s `_fail(...)` call —
one keyword, no exit-code churn, no change to `FAIL_CLOSED_REASONS` (which
`lock_timeout` was never in, before or after). `single_session_apply.py`'s
`freeze_splits_failed` branch already forwards the whole `freeze_result`
dict, so the marker reaches that caller too without a separate change.

### 10.2 (MEDIUM) — "all three lock users now share the underlying code" implied reentrancy that doesn't hold across all three — FIXED

True of the wait/lock loop, false of the same-thread reentrancy: only a
`FileLock` (sub)instance registers with the reentrancy registry, so
`_PhaseTasksLock` nests cleanly with itself, but `run_config_lock` /
`append_phase_history`'s `file_lock` — both the context-manager FUNCTION,
never a held `FileLock` instance — still self-exclude on a same-thread
nest against any of the three, unchanged from before this diff. No such
nesting exists today (verified by grep) — this was a doc overclaim, not a
live bug. Fixed: `_PhaseTasksLock`'s docstring and `run_config_store.py`'s
module docstring both now scope the reentrancy claim correctly.

### 10.3 (LOW/MEDIUM) — the `errno.EACCES` check doesn't narrow to "byte-range lock specifically" — FIXED (documentation)

CPython's Windows errno mapping sends several distinct causes (lock
violation, sharing violation, access denied, network access denied) all
onto `EACCES`, so a genuinely and permanently denied read matching that
shape is also retried for the bounded budget before raising — not just the
measured byte-range-lock case. Bounded cost either way. Docstring reworded
to state this honestly instead of claiming an exact match, mirroring the
"5 is ambiguous" trade-off `durable_publish` already accepts on the write
side.

### 10.4 (LOW) — the read-retry fix closes a race no two Shipwright components can hit against each other — FIXED (documentation)

Every lock target in the repo is a `*.lock` sidecar, never a file read
through `durable_read_text`/`durable_read_bytes` — the failure this guards
against can only come from a third party (AV, indexer, editor), never from
one in-repo lock user racing another. Docstring reworded to frame it as
defence in depth against an unmeasured third-party holder, not a closed
in-repo race.

### 10.5 (LOW) — the budget-exhaustion test was timing-dependent — FIXED

A real 0.02s budget with no `time.sleep` patch could lose its only retry
to scheduler jitter and fail misleadingly. Rewrote to drive a fake clock
(`sleep` advances the same counter `monotonic` reads), so elapsed time is
exact and deterministic — and the real `READ_RETRY_BUDGET_SECONDS` (2.0s)
is used instead of an arbitrary shortened value, since nothing actually
waits. Test wall-clock time for the whole file dropped from ~12s to ~1.6s
as a side effect.

### 10.6 (LOW) — one assertion in the freeze-failure regression test couldn't fail — FIXED

`freeze_splits` is stubbed to a pure no-write lambda in that test, so
`cfg["splits_frozen"] == []` held regardless of whether the production fix
worked. Removed; the load-bearing assertion (the design task's status
stays `in_progress`) is untouched and remains genuine.

### 10.7 (LOW) — the glob-based drift guard traded one staleness mode for another — FIXED

A glob removes "a new sibling goes uncovered" but introduces "a rename out
of the prefix, or any bug that shrinks the match, goes uncovered instead,
silently." Added a floor assertion (`len(paths) >= 5`) so an empty or
shrunk glob result fails loudly instead of just covering less.

### 10.8 (informational) — confirm the full plugin test suite ran as one process — CONFIRMED

Given this repo's history with same-root `sys.path` shadowing (ADR-044/045),
worth confirming `test_phase_tasks_lock.py`'s collection-time `sys.path`
insert was exercised inside a single full-root run, not per-file
invocations. Confirmed: `uv run pytest tests/` from `plugins/shipwright-run`
is the standing verification command used throughout this run (554 passed,
one process, most recently after the doubt-review fixes above).

## 11. External code-review cascade + bloat-gate remediation

**External code-review** (`external_review.py --mode code`, GPT + DeepSeek,
against the full staged diff): both **approve**, no findings — "no defects
found... all changes are well-reasoned and no security, correctness, or
regression issues are introduced" (deepseek); "ship-as-is" (openai).
Recorded as the `external_code` review type.

**Bloat gate, three offenders at the session Stop hook:**

- `phase_task_lifecycle.py` (660 → 725) and `test_single_session_loop.py`
  (306 → 349): both pre-tracked `grandfathered` baseline entries, growth
  already anticipated and named in §1. Refreshed `current` by hand (no
  tool regenerates a scoped subset without wiping other entries' `state`/
  `adr` fields — confirmed by reading `baseline_generator.py`, which is an
  onboarding-only full-repo regen).
- `atomic_write.py`: a genuinely **new** crossing (301 → 324) that no
  review pass caught, because it was already 301 lines at `HEAD` — 1 line
  over the guideline — before this run touched it at all (confirmed via
  `git show HEAD:...  | wc -l`), and the doubt-review docstring additions
  (D3, D4) pushed it further. Trimmed the new prose to the minimum that
  still names the mechanism, the measured shape, and the citation (net
  addition down from +43 to +23 lines) before concluding the remainder
  needed a real remediation, not more compression — see **ADR-127**
  (`.shipwright/planning/adr/127-bloat-exception-atomic-write-none-winerror-retry.md`)
  for the full Ousterhout / YAGNI / Chesterton-Fence argument for why an
  exception was chosen over extraction or further trimming of the
  pre-existing, incident-citing prose. Baseline entry added:
  `state: "exception"`, `adr: "ADR-127"`, `current: 324`.

Verified via the actual pre-commit checker, not just re-reading the
baseline file: `uv run shared/scripts/hooks/anti_ratchet_check.py --staged`
exits 0 against the full staged change set.
