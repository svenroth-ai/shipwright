# ADR-127: Bloat exception — `shared/scripts/lib/atomic_write.py` raised to 324-LOC

- **Status:** accepted
- **Date:** 2026-08-07
- **Re-Review-Date:** 2026-11-07
- **Incident Reference:** iterate-2026-08-07-lock-primitive-tail (trg-db1de213)
  — the read-side fix for a byte-range-locked read's `PermissionError`
  (`winerror=None`) not being retried, deferred by the prior iterate
  (iterate-2026-08-06-write-lock-primitives, trg-dc013d82 finding 10).

## Context

`atomic_write.py` is the shared `tmp + fsync + os.replace` durable-write
primitive every `shipwright_*` config/state/log writer routes through, plus
its Windows-specific retry logic for both the write side (a concurrent
reader defeating `os.replace`) and, as of this run, the read side (a
concurrent writer's in-flight replace, and now a byte-range lock, defeating
a read).

The file was **already at 301 lines at `HEAD`** — one line over the
300-line guideline — before this run touched it at all; no
`shipwright_bloat_baseline.json` entry existed, so it was an untracked,
un-triaged crossing that predates this diff. This run's fix (an opt-in
`retry_none_winerror` parameter on the shared retry predicate, wired
through the two read-path callers) is a small, surgical addition — net
+23 lines after aggressive trimming of the new docstring prose (see
Rejected Alternatives) — but it pushed an already-over file to 324.

## Ousterhout Argument

This is a genuinely deep module: the public interface is six functions
(`durable_atomic_write`, `durable_read_text`, `durable_read_bytes`,
`replace_retrying`, `sharing_violation_retries`, `reset_sharing_violation_retries`)
answering one question — "how do I durably read or write a file on a
platform where a concurrent reader or writer can transiently deny the
operation?" — and the substance behind that narrow interface is a single
shared retry/backoff loop (`_retry_past_sharing_violations`) plus the
fsync-ordering logic, both used identically by every caller. Splitting the
retry loop into its own module would not shrink the total prose (the
docstrings would still need to explain the SAME measured Windows failure
modes); it would only fragment one cohesive failure-mode story across two
files, and — concretely — break every existing test that monkeypatches
`aw._is_windows`, `aw.time.sleep`, or `aw.READ_RETRY_BUDGET_SECONDS`
directly on this module object (`test_atomic_write_windows_retry.py`,
`test_atomic_write_windows_read_retry.py`,
`test_atomic_write_read_winerror_none.py`), since a moved function would
read those names from a different module's scope. This is exactly the
fragmentation this run's OTHER bundled fix (`_PhaseTasksLock` delegating to
the shared `FileLock` instead of remaining a third copy) exists to avoid —
the module was deliberately built as the ONE shared home for these
primitives so a future fix touches one file, not several.

## YAGNI Check

Every one of the six public functions is actively called today:
`durable_atomic_write` (all JSON config/state writers), `durable_read_text`
/ `durable_read_bytes` (the read-side callers this run's fix targets, plus
`run_config_store.durable_read_text` re-export), `replace_retrying`
(public — `lib.sweep_drift_restore` renames the tracked log aside in the
same threat model, per its own docstring), `sharing_violation_retries` /
`reset_sharing_violation_retries` (asserted directly in tests — "an
unobstructed write retries zero times"). No speculative surface exists to
remove.

## Chesterton-Fence Check

The file's density is not accidental verbosity — nearly every paragraph
documents a SPECIFIC measured incident: the F0 race card
`f0-race:shipwright-run` (concurrent-reader-defeats-rename), the 12-concurrent-copy
starvation measurement behind the read/write budget asymmetry ("1 failure
in 36"), `trg-0a294ef3` (the retry counter), and now `trg-dc013d82`
finding 10 / `trg-db1de213` (the None-winerror read gap, including the
corrected assumption that a byte-range lock yields WinError 5, not 33).
Removing that prose to satisfy a line count would delete exactly the
non-obvious "why" documentation a future editor needs to not reintroduce
one of these already-fixed bugs — this repo's own `CLAUDE.md` singles this
class of comment out as the one worth keeping. The fence stands for a
documented reason; it is not being torn down.

## Decision

Raise `current` to **324** (this diff's actual line count, after trimming
the new prose to the minimum that still names the mechanism, the measured
shape, and the citation). Retirement plan: at the 2026-11-07 re-review,
check whether the accumulated Windows-retry incidents (now three: sharing
violations, read-vs-write races, byte-range locks) justify extracting a
`windows_retry.py` leaf module shared by both the write and read call
sites — a deliberate, reviewed extraction done on its own, not one forced
by a line-count deadline at the tail of an unrelated bug-fix run.

## Consequences

No other consumer changes: the module's public API is unchanged, only its
internal retry predicate gained one opt-in keyword argument. The bloat
gate's baseline now carries this entry, so the NEXT edit to this file is
measured against 324, not 300 — any future growth still ratchets and still
blocks, same as any other tracked file. Cost if the exception outlives its
re-review date: the file continues absorbing every future Windows-retry
measurement in one place, which is the intended shape, not a risk — the
re-review exists to confirm that is still true, not to force a split by
default.

## Rejected alternatives

1. **Extract `_retry_past_sharing_violations` into its own module now.**
   Rejected: would break three existing test files' direct monkeypatching
   of `aw.*` module attributes, forcing an unrelated, broader rewrite at
   the tail of an already fully-reviewed diff (self-review, Stage 1-3
   internal cascade, external plan + code review all already passed) — the
   kind of scope growth that would require re-running the review cascade
   for no behavioural benefit.
2. **Trim the pre-existing measured-incident prose to close the gap.**
   Rejected per the Chesterton-Fence Check above: several paragraphs are
   the only place a specific past measurement (failure rates, budget
   rationale, corrected assumptions) is recorded; deleting them to satisfy
   a line count trades a permanent knowledge loss for a temporary metric.
3. **Leave the file over the limit unresolved.** Rejected: violates the
   Iron Law this gate exists to enforce, and leaves the NEXT editor to
   discover the crossing by surprise instead of by a recorded decision.

---

## External Sources Acknowledged

This ADR follows `.shipwright/planning/adr/_template-bloat-exception.md`,
whose YAGNI Check + Chesterton-Fence Check headings are adapted from
obra/superpowers `writing-plans` (MIT, © Jesse Vincent) and
addyosmani/agent-skills `code-simplification` (MIT, © Addy Osmani).
