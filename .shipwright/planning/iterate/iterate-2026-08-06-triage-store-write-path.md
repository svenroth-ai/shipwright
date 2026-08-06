# Iterate: the tracked triage store's write path — four defects

- **Run ID:** `iterate-2026-08-06-triage-store-write-path`
- **Date:** 2026-08-06
- **Type:** change
- **Complexity:** medium
- **Card:** split out of `trg-79102ee3` (P2.19, IT-1 audit remainder)
- **Evidence:** `.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`
  findings **9, 16, 23, 25** (re-measured 2026-08-05, all four open)
- **Serial to:** P2.19e (also touches `reconcile_triage.py`)

## Why one iterate

All four sit on the **write path to the git-tracked triage store**, and three of
them fail the same way: a tool mutates `.shipwright/triage.jsonl`, something goes
wrong or is left undone, and the **delivery channel is silently switched off** —
`plan_main_tracked_drift` refuses `main_tracked_diverged`, and every subsequent
iterate's sweep returns `skipped`, delivering nothing, with no operator-facing
signal anywhere. The fourth (25) is the same value in a different currency: a
record is deleted rather than superseded, silently.

The unifying acceptance property is therefore: **no write on this path may
destroy a record or disable delivery without saying so.**

## Grounding — measured before fixing (the audit doc's own instruction)

Probe: `scratchpad/probe_findings.py`, run against the shipped code in this
worktree, 2026-08-06.

| # | Claim | Measured |
|---|---|---|
| 16a | `apply_gc` leaves main diverged | `plan_main_tracked_drift`: `no_drift` → **`refused: main_tracked_diverged`** ("4 HEAD line(s), 2 in the working tree") immediately after `apply_gc`. `git status` = `M .shipwright/triage.jsonl`. **Reproduced.** |
| 9 | `.bak` translates line endings | LF log (0 CRLF / 4 LF) → `.bak` written **4 CRLF / 0 LF**; `bak_bytes == original_bytes` is **False**. **Reproduced** — worse than "not durable": the recovery artifact is not a faithful copy of what it backs up. |
| 25 | same-id append deleted silently | two appends sharing an id but disagreeing on `originalTs`/`source`/`title` → one **deleted**, `warnings == []`. **Reproduced.** |
| 25 | real-corpus frequency | tracked log: 684 append lines, 684 distinct ids, **0** ids with >1 append. A collapse never fires on the *settled* log — only on a union (merge side / outbox), which is where it is unobserved. |
| 16b | reconcile has no rollback | code, `reconcile_triage.py:263-299`: `_atomic_write` at :264, commit at :292, **no restore on any failure branch**. |
| 23 | restore window open | code, `sweep_drift.py:242-254`: last read of the tracked file, then a *subprocess spawn*, then `git checkout --` overwrites. An append in between is destroyed and unobserved. |

The audit doc's two "gating facts" were **both stale** (a documented hazard for
this evidence file). Re-measured with `anti_ratchet.measure_worktree`'s own
counter: `triage_gc.py` is **300**, not 301; `worktree_isolation.py` is **370**,
matching its baseline `current: 370`. Neither blocks. But `triage_gc.py`,
`churn_merge.py` and `reconcile_triage.py` all sit at **exactly 300 of 300**, so
each fix must be delivered by *extraction*, not by growth — this shapes the whole
design below.

## Affected Boundaries

- **The tracked append-only log** `.shipwright/triage.jsonl` (`merge=union`,
  git-tracked, LF-vs-CRLF sensitive, read with `surrogateescape`).
- **The gitignored outbox** `.shipwright/triage.outbox.jsonl` — the real delivery
  channel, and the only durable place a salvaged line can go.
- **The main tree's git state** — index, HEAD, `.git/index.lock`.
- **The canonical triage `_FileLock`**, and the *non-cooperating* webui writer
  (`proper-lockfile`, directory-based) that does not compose with it.

## Acceptance Criteria

**AC-1 (finding 16a).** After `triage_gc --apply` leaves the tracked log
uncommitted, the tool prints a warning that names (a) the state, (b) the
consequence — `plan_main_tracked_drift` refuses and the sweep delivers nothing on
every later iterate — and (c) the remedy. Silence is a failure.

**AC-2 (finding 16a).** `triage_gc --apply --commit` folds the compaction into one
`chore(triage)` commit behind the same main-tree guards `reconcile_main_triage`
uses (no op-in-progress, not detached, nothing staged), and afterwards
`plan_main_tracked_drift` returns `no_drift`. Default stays warn-only.

**AC-3 (finding 9).** Both writes in `apply_gc` go through
`durable_atomic_write` (sharing-violation retries + parent-dir fsync), and the
`.bak` is **byte-identical** to the file it backs up — no newline translation.

**AC-4 (finding 16b).** When `reconcile_main_triage`'s commit definitively fails
(non-zero, not a timeout), the dedup rewrite is rolled back to the pre-rewrite
bytes *iff* the file on disk is still exactly what we wrote, and the result says
which happened. When it is not (a non-cooperating writer appended), nothing is
restored and the result says the delivery channel is now diverged. A timeout does
not roll back — git's state is unknown — and says so.

**AC-5 (finding 25).** `dedup_triage_lines` never drops a same-id `append`
silently. Appends that agree on an identity anchor are collapsed keep-last
(ADR-163 preserved) **with a warning**; appends that disagree are a probable
32-bit id collision between distinct items and are **kept**, with a loud warning
naming `triage_repair.py` — matching the twin `dedup_event_lines`, which already
refuses to drop for exactly this reason.

**AC-6 (finding 25).** Every caller surfaces those warnings.
`reconcile_main_triage` and the sweep's quarantine decision stop discarding them.

**AC-7 (finding 23).** The restore no longer overwrites the live file. It
`os.replace`s it aside atomically first, so whatever it held at that instant is
preserved; a late append found in the salvage is adopted into the outbox rather
than destroyed; a failed rename aborts the restore (`buffered`) instead of
overwriting blind; a failed `checkout` after the rename puts the file back. The
residual window that genuinely remains is documented **as data loss**, not as
unavoidable.

**AC-8 (`cross_component`).** One `category:"integration"` behavior proves the
components compose on a real git repo: GC → divergence warning → `--commit` →
`plan_main_tracked_drift` green → sweep delivers; plus a late-append salvage
driven end to end.

## Design

Three files are at exactly 300/300, so each fix ships as an **extraction plus the
fix**, following the precedent already set in `churn_merge.py:14-16`
(`triage_validate` was extracted for this same reason and re-exported so historical
import paths are unchanged).

| New module | Moved out of | Why |
|---|---|---|
| `lib/triage_gc_core.py` | `tools/triage_gc.py` | engine (vocabulary, plan, apply, validate) out of a CLI; gives both headroom |
| `lib/triage_dedup.py` | `lib/churn_merge.py` | `dedup_triage_lines` + the new collision rule |
| `lib/main_tree_guards.py` | `lib/reconcile_triage.py` | op-in-progress / detached / staged — reused by `triage_gc --commit` |
| `lib/sweep_drift_restore.py` | `lib/sweep_drift.py` | the salvage-rename restore |

Every moved name is re-exported from its old home, so no existing importer or
test changes its import.

**Not in scope** (named so the omission is a decision, not an oversight): the
`_op_in_progress` copy in `sweep_outbox.py` (finding 29, P2.19 remainder — that
file is at 296/300 and de-duplicating it is its own change); findings 14, 15,
17-22, 24, 26-28.

## Confidence Calibration

- **Boundaries touched:** the tracked append-only log `.shipwright/triage.jsonl`
  (git-tracked, `merge=union`, EOL-sensitive, read with `surrogateescape`); the
  gitignored outbox; a NEW transient sibling `.shipwright/triage.jsonl.salvage-*`;
  main's git state (index, HEAD); the canonical triage `_FileLock` and the
  non-cooperating `proper-lockfile` writer that does not compose with it.

- **Empirical probes run** (`scratchpad/probe_findings.py` unless noted):
  - 16a — `plan_main_tracked_drift` goes `no_drift` → `refused:
    main_tracked_diverged` immediately after `apply_gc`. **Reproduced.**
  - 9 — an LF log's `.bak` came back **4 CRLF / 0 LF**, `bak == original` False.
    **Reproduced**, and worse than "not durable": the recovery artifact was not a
    copy of what it backed up.
  - 25 — two same-id appends with different `originalTs`: one **deleted**,
    `warnings == []`. **Reproduced.**
  - 25 corpus — 684 append lines, 684 distinct ids, **0** multi-append ids; and
    **684/684 carry a valid `originalTs`** (JSON-parsed; a raw `"event":"append"`
    substring search returns 638 because it misses the spaced serializations — same
    1:1 property, different denominator, so always state the method). The second
    measurement is what settled
    the anchor rule after the Stage-1 rejection (see the mini-plan's Stage-1
    section): it removed the asymmetry the lenient arm was resting on.
  - Two same-microsecond `originalTs` pairs exist across DIFFERENT ids — the
    residual named in `lib/triage_dedup.py`'s docstring is real in its first half.
  - The audit doc's two "gating facts" were **both stale**: `triage_gc.py` is 300
    not 301, `worktree_isolation.py` is 370 = its baseline. Re-measured with
    `anti_ratchet.measure_worktree`'s own counter.
  - **Mutation probe on the finding-9 fix:** the write path was reverted to the
    hand-rolled tmp+fsync+replace + `write_text` backup, and 5 of 8 durability
    tests went red. The 3 that stayed green pin contracts (return shape, malformed
    JSON refusal), not the fix — stated so the count is not read as 8/8.
  - **Negative control for finding 23:** `test_a_bare_checkout_destroys_a_late_append`
    drives the OLD restore and asserts the line is gone, so the salvage tests
    cannot pass against a mechanism that was never needed.

- **Test Completeness Ledger:** in `shipwright_test_results.json`
  (`iterate_latest.test_completeness`) and carried in the F5c entry.

- **Confidence-pattern check:**
  - *Asymptote (depth).* Three review rounds hit this diff: two external plan
    rounds (13 structured findings) and the Stage-1 hard gate (5 divergences).
    Each round found something the previous had not, and the Stage-1 round found
    the most consequential one — a silent departure from an accepted revision
    that I had documented rather than escalated. Depth is not yet flat, which is
    why the code-review and doubt passes still run.
  - *Coverage (breadth).* Every one of the four findings has a unit pin, a
    fault-injection pin, and a place in the composition test. The failure paths
    the reviewers enumerated are individually covered (backup-write, publish,
    rename, checkout-with and without a reappeared file, adoption, missing log,
    commit failure with bytes unchanged and changed, timeout, CRLF, invalid
    UTF-8), plus an isolated-subprocess import smoke test over both the old
    re-export paths and the new module paths.
  - *Integration composition (`cross_component`).* One `category:"integration"`
    behavior: `shared/tests/test_triage_write_path_integration.py` drives
    GC → warning → a genuinely dead sweep → commit → a live sweep on a real git
    repo, plus late-append salvage, a collision blocking loudly, and a benign
    refresh still delivering. It asserts the property that spans all four
    modules, which no unit test can: **the delivery channel still works, and
    when it does not, something said so.**
  - *Known limit.* The residual restore window (a writer that opens the path by
    name between the rename and git's write) is narrowed, not closed, and is
    named as data loss in `lib/sweep_drift_restore.py` rather than as
    unavoidable. No test can prove its absence; the module says so instead.
