# Audit: the triage store + its outbox delivery surface (2026-07-28)

Referenced by triage card **`trg-…`** (see the card for the one-line summary). This
file is the detail. Two independent fresh audits of shipped code, one lens each:
data-loss and concurrency/atomicity. **33 findings raw, ~29 distinct** (both audits
independently flagged `triage_header` and `FileLock`).

## Why this audit exists

Two `work_completed` events from 2026-06-08 (`evt-b9b5ddf2` 16 found / 4 fixed;
`evt-bb598e0d` 20 / 8) still make the RTM report `| Unresolved findings | 24 |`, which
a `PreToolUse` hook (`check_security_scan`, shipwright-compliance) turns into a block
on **every** commit in this repo — the threshold is `enforcement.allowed_critical_findings`,
unset here, defaulting to 0.

The backing evidence was deleted: the campaign directory
`.shipwright/planning/iterate/campaigns/2026-06-08-triage-outbox-delivery/` exists in
neither the main tree nor any worktree (oldest surviving is 2026-06-10), and the ADR the
second event cites (**ADR-141**) was never minted — the highest real ADR file is 115.
Both event `commit` SHAs (`005f6438…`, `7a31e33c`) are pre-squash and **not ancestors of
main**. So the June list cannot be reconstructed, and this audit deliberately does not
try; it asks the answerable question instead: *does this surface hold real defects today?*

## What the archaeology established, independently of the audits

The remediation **is on main**, in the same campaign window:

| Commit | Evidence |
|---|---|
| `b8fcf8ae` | "harden D2 sweep/GC" — body reads *"Review-cascade remediation on the D2 sweep+GC (1 MED code + 2 MED + 2 LOW doubt)"*, enumerates FIX A–F, and carries `Run-ID: iterate-2026-06-08-outbox-delivery-d2` — the run of `evt-b9b5ddf2`. Confirmed an ancestor of main. |
| `8b36e7dc` | "residence-derived mark_status + reroute idle-main appenders (**D1 review cascade**)" |
| `41127433` | "empirical verification gate for outbox sweep/GC (≥200 real concurrency trials)" — the `-d2v` work of `evt-bb598e0d`, whose own event description records **"GATE PASS (all 5 methods)"** |
| `45ce4490` | "**D3 review cascade** — seam test, fail-soft decode, sweep-skip observability" |

**The root cause of the stale counter is structural, not clerical.** `review.fixed` is
written when the `work_completed` event is recorded (F5b) — *before* the remediation
commit exists. Fixes land afterwards, in their own commits. The event log is append-only,
so nothing can correct the field. The metric therefore **under-reports by construction**
for every run that takes its reviews seriously. Corroborating: only **4 of 389**
`work_completed` events carry a `review` block at all; the field was effectively
abandoned. Both audits reached the same conclusion independently — retire the counters on
this audit's evidence rather than on a reconstruction that cannot be made.

## Verification status — read this before fixing anything

**I verified 3 of 33 myself** (the three below marked ✅). The rest are reviewer claims.
This session repeatedly demonstrated what unverified claims are worth: the external code
review asserted a mechanism that was false, and I dismissed a correct finding using an
assertion that could not fail. **Ground each fix before making it.**

### ✅ Verified — high, small, and failing in the direction this surface was built to prevent

1. **`shared/scripts/lib/sweep_text.py:50` — strict decode in the sweep's reader.**
   `path.open("r", encoding="utf-8", newline="")` with **no `errors=`**, while the hardened
   sibling `jsonl_records.read_jsonl_records:159` uses `errors="surrogateescape"`. One
   invalid UTF-8 byte (a write interrupted mid multi-byte sequence — a cause
   `jsonl_records.py:150-153` names explicitly) raises `UnicodeDecodeError` out of
   `sweep_outbox_to_branch`, contracted "never raises for an expected condition". It
   detonates in `setup_iterate_worktree` **step 5** — after `git worktree add` succeeded
   and before `write_snapshot`, leaving an orphaned worktree and an iterate that can never
   pass the leak-guard. *Fix:* `errors="surrogateescape"`; round-tripping surrogates
   through `normalize_lines` → `durable_atomic_write` is byte-preserving.
2. **`shared/scripts/lib/triage_header.py:48-52` — truncate-then-write on the tracked SSoT.**
   `path.read_text(...)` then `path.write_text(line + existing, ...)`; `write_text` opens
   `"w"`, i.e. truncates first. The only whole-file rewrite of the git-tracked
   append-only store that bypasses `durable_atomic_write`, and it sits on a *recovery*
   path. A crash in that window leaves the store empty. It also translates newlines, so on
   Windows an LF log is rewritten CRLF — a whole-file diff on a `merge=union` artifact,
   the class `triage_repair.py:19-25` warns about. *Fix:*
   `durable_atomic_write(path, line + existing)`, reading via `read_text_verbatim`.
3. **`shared/scripts/lib/sweep_outbox.py:133 → :233` — the GC rewrites the outbox from a
   stale read.** The outbox is read once at `:133`; `git add` + `git commit` run in between
   (`timeout=120.0` at `:212`, sized for the cold `uv run` pre-commit hook); `:233`
   `durable_atomic_write(outbox_path, survivor_text)` publishes survivors computed from the
   stale list. An append landing in that seconds-to-two-minutes window is destroyed: the
   outbox is gitignored (no history), the line never reached a branch, nothing quarantines
   it, and the sweep reports success. `gc_dropped > 0` is the steady state, so the
   `if gc_dropped or quarantined:` guard rarely helps.
   *Two things make this a defect rather than an accepted trade-off:* the sibling
   `sweep_drift.commit_main_tracked_drift:256` **re-reads the outbox** before its own write,
   20 lines earlier in the same critical section, with the comment "A process lock cannot
   stop an external `git commit` or an editor"; and the manual `triage_repair.py:258-267`
   **refuses `--apply` without `--writers-quiesced`** for exactly this hazard. The
   automatic sweep does it unprompted at every iterate setup.
   *The non-cooperating writer is real and in-repo documented:* `triage_repair.py:30-36` —
   "The webui writer uses `proper-lockfile` (directory-based), which … does NOT compose
   with the Python `msvcrt`/`fcntl` byte-lock". That writer is the operator's primary
   dismiss surface. The invariant-1 claim at `sweep_outbox.py:14-17` holds only for
   writers that take the Python lock, and the concurrency proof
   (`test_sweep_outbox_concurrency.py:39-42`) drives a cooperating writer.
   *Fix:* re-read the outbox immediately before computing survivors, exactly as
   `commit_main_tracked_drift` already does.

### Reported, unverified — cheap and local if they hold

4. `jsonl_records.py:88-94` — `ends_without_newline` catches `(OSError, ValueError)` → `False`
   ("safely appendable"), a fail-**open** on the *prevention* half of the newline fix. A
   Windows delete-pending `PermissionError` therefore skips the separator → two records on
   one line. *Fix:* only `FileNotFoundError`/empty → `False`; any other `OSError` → `True`.
5. `jsonl_records.py:159` — `read_jsonl_records` uses a bare `open`, not `durable_read_text`,
   which `atomic_write.py:176-191` says callers of `durable_atomic_write`-published files
   should use. Unlocked readers (`hooks/check_drift.py:348`, `tools/aggregate_triage.py:353`,
   `tools/triage_cli.py:77`, `github_triage/resolve.py:64`, `phase_quality/_triage_bundle.py:244`)
   race the sweep's rewrite; the Windows window was measured 1-in-36 in that docstring.
6. `reconcile_triage.py:231-233` — the `git commit` runs at `run_git`'s default
   `timeout=15.0`, while `sweep_outbox.py:205-214` documents that this same commit's
   pre-commit hook "routinely exceeds run_git's 15s default" and uses 120 s **plus** a
   `TimeoutExpired` handler. Reconcile has neither: the exception escapes a
   never-raises contract, and `run_git`'s `proc.kill()` strands `.git/index.lock` in the
   operator's **main** tree. *Fix:* mirror the sweep.
7. `sweep_outbox.py:189, 198, 223` + `sweep_gc.py:32` — only the `commit` is wrapped
   against `TimeoutExpired`; `git add`, `git diff --cached` and `git show origin/…` run at
   15 s bare, as do the four `run_git` calls in `plan_main_tracked_drift`. Same step-5
   crash as finding 1. *Fix:* wrap the whole locked section.
8. `artifact_sync.py:110-123` — `text=True` with **no `encoding=`** (cp1252 on Windows, the
   pattern already fixed at `github_api.py:80`), **no returncode check** (a bad ref or an
   index lock yields empty stdout → `drift_detected: False`, so a git failure reads as a
   clean tree and silently suppresses the drift producer), and **no `timeout=`**.
   *Fix:* route through `lib.git_base.run_git`.
9. `triage_gc.py:222-233` — `apply_gc` hand-rolls tmp + fsync + `os.replace` instead of
   `durable_atomic_write`: no Windows sharing-violation retry, no parent-dir fsync, and its
   `.bak` uses `write_text` (not durable, not newline-neutral).
10. `atomic_write.py:73` — `_SHARING_VIOLATION_WINERRORS = {5, 32}` omits **33**
    (`ERROR_LOCK_VIOLATION`), which CPython also maps to `PermissionError`.
11. `triage_header.py:20-34` — `has_header` reads the **entire** file to inspect line 1, on
    every tracked append, inside the canonical lock (~0.5 MB here). Its `except OSError:
    return False` is a fail-open on a *write* decision: a transient probe failure followed
    by a successful read prepends a **second** header. *Fix:* `fh.readline()`; let a
    non-`FileNotFoundError` propagate.
12. `triage.py:600` — `should_route_to_outbox` spawns three git subprocesses **inside** the
    lock (~100-300 ms on Windows) on every status flip; nothing in that decision depends on
    the locked state. *Fix:* hoist above the `with`.
13. `reconcile_triage.py:227-230` — obsolete comment naming `_unrelated_staged`, which does
    not exist (it is `_has_staged_changes`, `:98`), and the guard is evaluated *outside* the
    lock, so it is advisory.

### Reported, unverified — each is its own design change, not a fix

14. **`sweep_gc.py:63-78` — `is_delivered` drops a line that was never delivered.** An
    append is considered delivered **iff its id is in origin**, not iff its content is. The
    docstring's premise ("immune to a future producer re-serializing the SAME logical
    append") is contradicted by `churn_merge.dedup_triage_lines:160-177`, which exists
    *because* same-id non-identical appends happen and names the incident ("the
    trg-60ef91fb double-append that blocked the 2026-06-08 delivery"). Claimed live
    evidence: of 443 append lines in `.shipwright/triage.jsonl`, exactly one has
    `ts != originalTs` plus a `+00:00` suffix `triage._now_z()` cannot emit — line 285,
    `trg-60ef91fb`. **This specific claim is unverified by me; check it first.** If it
    holds, a refreshed v2 for an id already in origin is GC'd from the outbox after being
    committed to a branch that is later abandoned → the record exists nowhere.
15. `triage_validate.py:54-62` — `classify_triage_text` does per-physical-line `json.loads`
    with **no** boundary recovery, while the reader has it and the events-log twin was
    fixed to use `split_records` (`churn_merge.py:249`). One concatenated line → `block` →
    **nothing is delivered, this run or any future run**, stranding every unrelated
    buffered dismiss, while `read_all_items` recovers the record perfectly so the board
    shows it as applied. The operator-facing string never names `triage_repair.py`.
16. `triage_gc.py:217-233` + `sweep_drift.py:199-206` — `apply_gc` rewrites main's tracked
    log **without committing**, so `plan_main_tracked_drift` then reports
    `refused: main_tracked_diverged` and the sweep returns `skipped` **on every subsequent
    iterate** until someone commits the compaction. Same terminal state if
    `reconcile_main_triage`'s commit fails after its rewrite (`reconcile_triage.py:216-235`,
    no rollback). Neither tool warns that it just disabled the delivery channel.
17. `sweep_quarantine.py:95-107` — `protected_status_unplaceable` blocks forever and the
    remedy it prints ("deliver main (push / merge origin)") is unreachable in this
    workflow, because main is not pushed directly. Absorbing state; the buffer is one
    `git clean -xfd` from empty.
18. `triage_validate.py:89-93` + `sweep_quarantine.py:95-97` — a `status` line with a
    missing/non-`str` id records the orphan error but is not added to `orphan_status_ids`,
    so `decide` returns `block`; it can be neither quarantined (needs the id) nor repaired
    (`needs_repair` is false — the JSON is valid). Terminal.
19. `github_triage/resolve.py:64-89` (also `:109`, `:165`) — unlocked read-modify-write
    across a process boundary: `read_all_items()` with no lock, then N flips each under its
    own acquisition. An operator re-open landing mid-sequence is clobbered, and
    `read_all_items` pass-2 is `ts`-primary so the importer's later `dismissed` **wins**.
    Same shape in `tools/accepted_risks_converge.py:44`,
    `phase_quality/_triage_bundle.py:244`, `tools/suite_race_triage.py:103`. Root cause:
    `mark_status` offers no "flip only if still `triage`". *Fix direction:* add
    `expected_status` checked inside the existing lock — four callers.
20. `atomic_write.py:113` — `tempfile.mkstemp` creates at `0600` and `os.replace`
    publishes it, so **every** file this primitive rewrites silently loses group/other read
    bits on POSIX, invisibly to git. ~30 call sites, not just triage.
21. `jsonl_records.py:123-133` — boundary recovery is **one-directional**: an unrecoverable
    *prefix* discards every valid record after it on that line. The primary documented
    cause is a truncated predecessor, i.e. exactly that shape. The two covering tests
    (`test_triage_newline_integrity.py:92`, `:128`) exercise complete-prefix and
    garbage-on-its-own-line — the failing shape is untested.
22. `triage.py:255-264` — `_iter_raw_lines_at` warns on each `CorruptFragment` then
    **discards** `result.corrupt`, so for every `read_all_items` consumer an unrecoverable
    fragment still reads as absence — the invariant `jsonl_records.py:17` states as "on an
    append-only log, corruption must never read as absence". `warnings.warn` is globally
    suppressible.
23. `sweep_drift.py:263-273` — the pre-restore re-verification narrows but does not close
    the window; an append from a non-cooperating writer landing after the re-check and
    before `git checkout --` is destroyed. Framed as unavoidable rather than as data loss.
24. `file_lock.py:151-165` — `FileLock` has **no timeout** and **no reentrancy**: POSIX
    `flock(LOCK_EX)` blocks forever, Windows spins a 1 ms loop forever. A nested
    acquisition self-deadlocks with no diagnostic (traced: none exists today). It also
    truncates its own sidecar (`"w"`). The sibling `file_lock()` in the same module has a
    hard 5 s timeout and documents why.
25. `churn_merge.py:204-216` — `dedup_triage_lines` is the one path that **deletes** a
    record rather than superseding it (keep-last on same id). Ids are `uuid4().hex[:8]` =
    32 bits; ~1.2% collision probability at 10 000 appends, and the log is append-only. The
    sibling `dedup_event_lines:150-156` **refuses to drop** in exactly this case and warns,
    citing 32-bit ids. Reasoned, not constructed.
26. `triage.py:688-692` and `triage_gc.py:107-111` — pass-2 partial overlay: `status` is
    gated on the enum but `ts`/`statusBy`/`statusReason` are assigned unconditionally, so an
    out-of-enum status event replaces the actor and rationale of a real decision — and
    `triage_gc.is_machine_churn:73-79` keys its **delete** decision on exactly those two
    fields. Unsound; nothing reaches it today.
27. `sweep_gc.py:63-78` — `status`/unparseable lines still GC by **text only**, so any
    re-serialization makes one permanently un-GC-able: the gitignored buffer grows
    monotonically with no bound and no signal.
28. `triage_cli.py:85-91` — `pendingDelivery` counts appends only, so an item whose *status
    flip* is stranded simply drops off the board, reading as decided-and-done. **There is no
    surface anywhere that says "your dismiss has not reached origin."** This is what makes
    findings 3, 15-18 quiet rather than loud.
29. Duplication (catalog **D**): `_op_in_progress` byte-for-byte in `sweep_outbox.py:64-79`
    and `reconcile_triage.py:72-91` (the former's docstring says "Mirrors" the latter);
    `_has_staged_changes` duplicated; `_CI_TRUTHY`/`_ci_active` in **three** copies. Three
    git-state predicates gating destructive commits, maintained in parallel — `sweep_outbox`
    already lacks reconcile's `_is_detached`. ~34 LOC recoverable.

### Gating facts to confirm before touching those files

- `shared/scripts/tools/triage_gc.py` measured **301** lines against the 300 limit and is
  **absent from `shipwright_bloat_baseline.json`** → a new crossing (Group H1) that blocks a
  Stop hook on touch.
- `shared/scripts/lib/worktree_isolation.py` measured **371** against baseline
  `current: 370` → an anti-ratchet violation that blocks the next commit staging it.
- Measure both with `python -c "print(open(p,'rb').read().count(b'\n'))"` — the exact
  measure `anti_ratchet.measure_worktree:35` uses — before acting.

## What both audits attacked and could NOT break

Recorded because a claim tested and not broken is evidence, not silence.

- **The locking model is sound.** One lock held across plan → read → materialize → adopt →
  commit → GC with every `return` inside the `with`; cross-process **and** cross-thread on
  both platforms; releases on process death (no stale-lock wedge); **no double acquisition
  anywhere today** (every locked body traced, plus a grep over all 92 triage-importing
  files — the pre-commit hook runs only `anti_ratchet_check.py`, which does not import
  `triage`).
- **`durable_atomic_write` is correct on Windows** — bounded sharing-violation retry that
  clamps its last sleep and re-raises, temp removed and original error re-raised on
  failure, so `path` never points at a half-written temp.
- **Read-modify-write under lock is careful** where it matters: `append_triage_item_idempotent`,
  `triage_gc.apply_gc` (recomputes the drop set under the lock over the union and validates
  against the effective set — a genuine TOCTOU fix), `triage_repair --apply`, `mark_status`.
- **Git index isolation across the worktree boundary is real** — distinct index files and
  ref locks; shared-`.git` contention returns non-zero and is mapped loudly.
- **The plan-then-commit ordering is crash-safe** in the direction that matters (outbox
  written durably *before* the tracked-log restore; a replay dedups). Both audits called
  this the strongest-built part of the surface.
- **Invariant 2 is fail-safe against loss** — unreadable origin GCs nothing; a stale origin
  only ever keeps lines. The only break found is by *content* (finding 14), never by
  reachability.
- **Status-before-append ordering** survived interleaved union-merge orders, cross-file
  flips and equal-`ts` ties.
- **EOL handling is coherent** end to end.
