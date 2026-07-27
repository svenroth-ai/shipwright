# iterate-2026-07-27-run-unit-parallel-race

- **Run ID:** `iterate-2026-07-27-run-unit-parallel-race`
- **Intent:** BUG (Path C -> F-debug)
- **Complexity:** medium (`prior_source: history`, n=20)
- **Spec Impact:** MODIFY — `durable_atomic_write` gains a documented Windows
  contract; the module docstring currently asserts something untrue.
- **Trigger:** F0 race card `f0-race:shipwright-run` — "red in parallel (rc 1),
  GREEN alone (rc 0) … NOT xdist-allowlisted, so this is inter-unit pollution or
  an unreliable test. Both are real defects; only measurement separates them."

## Verdict on the card's question

**Neither.** It is a genuine product bug in the shared atomic-write primitive,
surfaced (not caused) by CPU contention. The test that goes red is correct and
must not be weakened.

## F-debug Phase 1 — Read Error

> **Provenance, stated because it matters.** The traceback below is from **this
> iterate's own 12-copy reproduction**, not from the run that filed the card.
> The original failure's output was never captured: `suite_report.entry_detail`
> deliberately excludes test output from the tracked card, and the console it
> went to belonged to a different worktree (`.worktrees/adopt-derived-catalogue`)
> at a different commit (`49237e82`). So this is the traceback of *a* failure of
> that unit under contention, reproduced here — not proof that it is the *same*
> failure the card saw. See "What is NOT established" below.

```
File "shared/scripts/lib/atomic_write.py", line 55, in durable_atomic_write
    os.replace(tmp, path)
PermissionError: [WinError 5] Access is denied:
  '...\shipwright_run_config.json.hwns1lw0.tmp' -> '...\shipwright_run_config.json'
FAILED tests/test_runconfig_concurrency.py::test_three_process_writers_no_truncation_no_lost_update
```

- **Error site:** `plugins/shipwright-run/tests/test_runconfig_concurrency.py`
  (`assert p.returncode == 0`).
- **Error source:** `shared/scripts/lib/atomic_write.py:55` — `os.replace`.
- **Observed:** a run-config write raises `PermissionError` and is lost.
- **Expected:** the write lands; concurrent readers never make a writer fail.

## F-debug Phase 2 — Reproduce

Stochastic (as reported), then narrowed to deterministic.

| Experiment | Samples | shipwright-run result |
|---|---|---|
| Full F0 suite in parallel, faithful (18 units, budget 22) | 5 rounds | 5/5 **green** — no race flagged in any unit |
| 12 concurrent copies of **only** shipwright-run, pre-fix | 48 | **1 failure (2.1%)** |
| Single reader holds the destination open, pre-fix | 1 | **100% failure** |
| 12 copies, **write fix only** (2.0 s budget) | 72 | 0 failures |
| 12 copies, **write fix only** (0.5 s budget) | 48 | **1 failure — in the READER**, `load_run_config` |
| 12 copies, write fix + read fix, both budgets 0.5 s | 36 | **1 failure — reader starved** |
| 12 copies, **final**: write 0.5 s + read 2.0 s | **96** | **0 failures** |
| Single reader that releases after 150 ms, post-fix | 1 | write lands in 0.160 s |
| Single reader that never releases, post-fix | 1 | raises after the budget, no debris |

The middle two rows are why this took four measurement rounds rather than one:
each fix moved the failure somewhere new, and only re-measuring after every
change exposed the next face. A single post-fix green run would have shipped
the reader bug.

The 12-copy experiment ran **no sibling unit at all**, which excludes inter-unit
pollution *for that configuration*.

**The load-bearing evidence is the deterministic repro (100% → 0%), not the
rate data.** 0-in-72 is weak on its own: at the observed 2.1% rate an *unfixed*
build yields zero failures in 72 samples about 22% of the time
(`(47/48)^72 ≈ 0.22`), and the rule of three puts the 95% upper bound at
3/72 = 4.2% — above the pre-fix point estimate. The contention samples are
corroboration; they cannot by themselves distinguish "fixed" from "unlucky".
What settles it is that a single open reader failed 100% of the time before and
0% after, with the mechanism instrumented end to end.

Deterministic repro (fails before the fix, passes after):

```python
target.write_text('{"v": 1}', encoding="utf-8")
reader = open(target, "r", encoding="utf-8")   # any reader at all
durable_atomic_write(target, '{"v": 2}')        # PermissionError winerror=5 errno=13
```

## F-debug Phase 3 — Recent Changes

**Not a regression.** `atomic_write.py` has carried this behaviour since it was
introduced; `git log` shows no recent change to the replace path. What changed is
exposure: the F0 suite runner now runs 18 units concurrently, which widens the
window in which a reader and a writer overlap. The bug was always reachable —
two Shipwright processes on Windows (a hook plus the orchestrator, or the WebUI
reading while the orchestrator writes) hit it without any test involved.

## F-debug Phase 4 — Component-Boundary Instrumentation

Boundary where good input becomes bad output: `os.replace(tmp, path)`.

`atomic_write.py:42` states the premise "`os.replace` onto `path` (**atomic on
POSIX and Windows**)". On Windows that is only true when the rename *succeeds*:
Windows refuses to replace a file that any process holds open without
`FILE_SHARE_DELETE`, and CPython's `open()` does not request it. The run-config
design **deliberately permits unlocked readers** —
`orchestrator_pkg/step_planning._read_standalone_flag` reads
`shipwright_run_config.json` outside `run_config_lock` on every `update_step`
call, documented as safe because it does not write. It is safe against *lost
updates*; it is not safe against *Windows rename semantics*. External readers
(WebUI, editors, antivirus, indexers) are outside our locking discipline
entirely, so no amount of internal locking closes this.

**Root cause (one sentence):** `durable_atomic_write` treats `os.replace` as
infallible, but on Windows it fails with `PermissionError`/`WinError 5` whenever
any process has the destination open, so a legitimate concurrent *reader* makes
a *writer* lose its write.

### The root cause has two faces — found by re-measuring after the first fix

Hardening the writer alone **moved** the failure instead of removing it. Re-running
the 12-copy experiment against the fixed writer produced the same test failing at
the same rate, but in a different place:

```
config_io.py:47 in load_run_config
    config = json.loads(path.read_text(encoding="utf-8"))
PermissionError: [Errno 13] Permission denied: '...shipwright_run_config.json'
```

The mirror image of the same Windows semantics: when a writer replaces a file
that someone still holds open, the old directory entry goes **delete-pending**,
and a reader's `open()` then fails until the last handle closes. And the first
fix plausibly made this *more* reachable — before it, a contended write failed
and no replace happened at all; after it, more writes succeed, so more of these
windows exist.

So the complete statement is: **on Windows the unlocked run-config read and the
run-config write can each be defeated by the other, and both need the same
bounded tolerance.** The write side is `durable_atomic_write`; the read side is
the new `durable_read_text`, used at the three run-config readers
(`config_io.load_run_config`, `phase_task_lifecycle._read_config`,
`append_phase_history`). A read that stays unreadable past the budget still
raises — degrading to `""` would be worse than the crash, because callers treat
an unparseable config as "first run, no config yet" and would bootstrap over a
live pipeline.

This is also why the budget was NOT the lever: the reader failure appeared at
0.5 s and not at 2.0 s, but at ~2% rates those two samples are statistically
indistinguishable, so the budget change cannot be credited or blamed for it.

## Acceptance Criteria

- **AC1** `durable_atomic_write` completes successfully when the destination is
  transiently held open by a reader that releases it within the retry budget.
- **AC2** When the destination stays held past the budget, the call still raises
  `PermissionError` — the write is never silently dropped and never partially
  applied.
- **AC3** No temp-file debris is left behind on either outcome. *Best-effort on
  Windows:* the cleanup `os.unlink` can itself hit a sharing violation (the
  just-written temp is the likeliest thing an AV scanner has open) and that
  error is suppressed so it cannot mask the real one. In that case a `.tmp`
  file survives. Stated rather than asserted away — `.gitignore` carries no
  `*.tmp` pattern, so such a file would show up as untracked.
- **AC4** On POSIX the behaviour is unchanged: a genuine `PermissionError` from
  `os.replace` propagates immediately and is not retried away.
- **AC5** The module docstring no longer claims unconditional Windows atomicity;
  it states the real contract.
- **AC6** `plugins/shipwright-run` stays green when 12 copies run concurrently.
- **AC7** The retry never outlives `REPLACE_RETRY_BUDGET_SECONDS`: the backoff
  sleep is clamped to the time actually remaining.
- **AC8** Neither the fix nor its tests depend on patching `os.name`; the module
  branches on one mockable predicate, so Linux CI exercises the Windows path
  without `pathlib` raising `NotImplementedError`.
- **AC9** A run-config **read** survives a concurrent writer's in-flight
  `os.replace` (the delete-pending window), and a file that stays unreadable
  past the budget still raises rather than degrading to an empty string.

## What is NOT established

Stated explicitly so the card is not closed on more confidence than exists:

1. **That this bug is what the card saw.** The original failure was never
   reproduced (5/5 green in the faithful 18-unit configuration) and its output
   was never captured. A genuine `os.replace` bug in that unit's write path was
   found and fixed; whether the card's specific red was *this* red is
   unestablished and now unknowable from the record.
2. **That inter-unit pollution is absent from the 18-unit run.** It was excluded
   only for the 12-copy reproduction, which is not the configuration the card
   describes. Real pollution does exist in the shared tree —
   `plugins/shipwright-security/.shipwright/` is written into the repo by that
   unit's tests and is not gitignored — filed as `trg-c6e75011`. The suite
   runner has no working-tree-dirty detection, so that whole class is currently
   invisible to the gate.
3. **That the rate is now zero.** See the Phase-2 note: 0/72 cannot demonstrate
   that.

Accordingly the race card is left to the operator to close or dismiss, per its
own rule that one clean parallel run is not evidence — this iterate supplies a
fixed mechanism and the measurements, not a closure.

## Findings raised in review and deliberately declined

- **Split into two commits** (code-reviewer, bisectability). Declined: the F11
  verifier checks a single F6 commit, so a two-commit branch fails finalization.
  The two concerns are kept as separate self-contained hunks and named
  separately in the commit body instead.
- **Add a `windows-latest` CI leg** (code-reviewer). Declined here: it changes
  `.github/workflows/**`, which trips the `touches_ci_supplychain` risk flag and
  its posture-acknowledgement gate — a deliberate decision of its own, not a
  rider on a bug fix. The injected-failure tests give Linux CI real coverage of
  the retry logic; only the real-OS fidelity test is developer-local.
- **Emit a signal on a successful retry** (doubt-reviewer, high). Declined as
  built-here: adding a telemetry channel to a primitive with 30 call sites is a
  design decision with no consumer today (YAGNI). The blind spot is now named in
  the module docstring so it is visible rather than implied.
- **Widen the winerror set to 33 / 1224** (code-reviewer). Declined on evidence:
  measured on Windows 11, a memory-mapped holder and a byte-range lock both
  surface as `PermissionError` winerror **5**, not 1224/33 — the premise did not
  reproduce.

## Out of scope / separately flagged

`shipwright-changelog` is **deterministically red on Windows** on base commit
`97392eea` (main), independent of this bug and of concurrency. It is fixed here
only because F0 cannot go green otherwise, and is kept as a separate,
self-contained hunk.

Root cause: **the child's stdio encoding, not the characters in the message.**
On a pipe the child picks the locale codec (cp1252) while every reader in this
repo decodes utf-8, so an undecodable byte kills `subprocess`'s reader thread
and the caller gets `stderr = None` — a crash instead of the reason the release
stopped (measured: `stderr is None` is True, the caller does not get an
exception).

The first attempt here sterilised the two em-dash literals. **Both reviewers
rejected it as a symptom patch and they were right:** the refusal message
interpolates operator-supplied data (`{changelog_path}`, `{version}`), so a
project under a non-ASCII path re-breaks it. Verified against the pre-fix module
with a `Müller-Projekt` directory — stderr carries `0xfc` at position 61, before
the em-dash at 174. The fix is therefore at the source (the CLI pins stdout and
stderr to utf-8) and the regression test uses a non-ASCII project directory, so
it asserts a property of the code rather than of the fixture.

## Confidence Calibration

- **Boundaries touched:** the `tmp + fsync + os.replace` file-publication
  boundary in `shared/scripts/lib/atomic_write.py` (30 caller sites: run config,
  loop state, triage log, events log, changelog, coverage, bloat baseline);
  the child-process stderr byte boundary in `shipwright-changelog`.
- **Empirical probes run:**
  1. `open(lock, "w")` while a peer holds byte 0 — **hypothesis disproved**:
     Windows allows the truncating open and `msvcrt.locking` still refuses
     correctly (`PermissionError`), so `_PhaseTasksLock` is not the bug.
  2. `update_step` non-`complete` branch — **hypothesis disproved**: the
     `in_progress` RMW is fully inside `run_config_lock`; no unlocked write.
  3. Reader-holds-destination + `durable_atomic_write` — **confirmed**,
     `PermissionError winerror=5 errno=13`, 100% reproducible, no debris, prior
     content intact (write lost, not corrupted).
  4. Raw stderr bytes from `changelog.py` — **confirmed**, byte `0x97` at
     position 159 (cp1252 em-dash), parent utf-8 decode kills the reader thread
     and yields `result.stderr is None`. Re-verified after review challenged the
     mechanism (the suggestion was that CPython raises `IndexError` instead):
     directly observed `stderr is None` is True on Python 3.12.13, so the
     recorded mechanism stands. Re-run against a **non-ASCII project path**, the
     pre-fix module emits `0xfc` at position 61 — earlier than the em-dash —
     which is what proved the literal-only fix insufficient.
  5. 5 faithful parallel F0 rounds + 48 self-contention samples — quantified the
     natural rate at 2.1%, which is why "one clean run" proves nothing.
  6. `pathlib` platform dispatch — **confirmed**, and it invalidated the first
     version of these tests. Patching `os.name` to force a branch is
     process-global: `PosixPath` carries a raising `__new__` on a Windows host
     and `WindowsPath` carries one on POSIX (bound at class-definition time), so
     `durable_atomic_write`'s `path.parent` raises `NotImplementedError` before
     any code under test runs. Observed live here in the `"posix"` direction;
     the `"nt"` direction would have been green on Windows and **red in Linux
     CI**. Closed by branching on a single mockable `_is_windows()` predicate;
     the two pre-existing tests that used the same fragile patch were migrated
     to it as well.
  7. Retry-budget arithmetic — the backoff could sleep up to one step PAST the
     deadline and then attempt one more replace, so the effective window
     exceeded the configured budget. Clamped to the remaining time and pinned by
     `test_retry_never_outlives_the_configured_budget`.

  Probes 6 and 7 came from the external code review (GPT-5.4 via OpenRouter,
  verdict `revise`). Gemini returned an empty reply and is recorded as
  **degraded** — only one external reviewer answered, so the external leg is
  single-sourced and the subagent cascade carries the weight.
- **Test Completeness Ledger:** see `shipwright_test_results.json`
  (`iterate_latest.test_completeness`); every behaviour below is `tested`.
- **Confidence-pattern check:**
  - *asymptote (depth)* — the causal chain is instrumented end to end: reader
    handle -> `os.replace` -> `WinError 5` -> lost write -> failing assertion.
    Both competing hypotheses were killed by probe, not by argument.
  - *coverage (breadth)* — retry-success, retry-exhaustion, POSIX
    non-retry, and debris-free failure are each pinned by an
    injected-failure test that runs on every platform, so Linux CI exercises
    the logic that only misbehaves on Windows.
  - *integration composition* — not applicable: `cross_component` is not set
    (`atomic_write.py` matches no `CROSS_COMPONENT_FILE_PATTERNS` entry), and
    the real multi-process composition is already covered by the existing
    `test_runconfig_concurrency.py`, which is the test that caught this.
