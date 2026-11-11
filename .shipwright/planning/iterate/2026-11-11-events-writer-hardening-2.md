# Iterate Spec: events-writer-hardening-2

- **Run ID:** iterate-2026-11-11-events-writer-hardening-2
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal
Second hardening round of the per-run event files (`shipwright_events.d/`): the modules that name, read, stage,
fold and check those files agree on one file-name rule, a run's events keep their order across a file rotation,
and a writer never appends to a file whose last line is half written.

## Findings (checked against the code, probed with tests before any fix)
1. **Three different drop-name patterns.** `events_read` and `events_stage` accept any key (`.+`, ending in `$`);
   `events_fold_io` (fold, quarantine, integrity check) accepts only the keys the writer produces (ending in `\Z`);
   the writer checks its own name with a fourth, looser class. A file the writer would never name is staged by one
   tool, read as a keyed drop by another, and refused by the integrity check. Real, fixed here.
2. **CRLF under `core.autocrlf` (listed by the operator): not a defect.** Fold, quarantine and the integrity check
   already compare modulo line ending (`same_bytes`), pinned by `test_a_crlf_checkout_still_folds`,
   `test_quarantine_works_on_a_crlf_checkout` and the integrity autocrlf test. Nothing changes; recorded so the item
   is not re-opened.
3. **Order across a rotation.** After a commit closes a run's drop, the next event goes to a NEW file. The
   monotonic-`ts` guard only looks at the open file, so on a coarse clock the new event can tie with the closed
   file's last event and the reader (instant, then random id) can put it BEFORE it. Reproduced.
4. **Torn open drop.** A drop whose last line was cut short (crash mid-write) is still chosen as the open drop; the
   writer glues a newline on and appends, so the damaged file keeps growing. Reproduced.

## Acceptance Criteria
- [ ] AC1 One definition of a drop file name (`DROP_NAME` in `lib/events_read.py`, built from `KEY_MAX`, anchored with
  `\Z`) is used by the writer's own check, the reader, the staging tool, the fold, the integrity check and the F11
  own-worktree test; a name is accepted or refused by all of them alike (a name with a trailing newline included).
- [ ] AC2 Whenever a run opens a NEW drop (after a commit closed the old one, or because the open one was torn), its
  first event is read back after every earlier event of the same run key, in any worktree, even with an equal
  timestamp: first `ts` = max `ts` over the run key's drops + 1 microsecond when it is not already greater.
- [ ] AC3 A drop that is non-empty and does not end in a newline (torn) is never appended to and is left byte for
  byte unchanged; the next event goes to a new file and later events of the run go to that same new file.
- [ ] AC4 The legacy layout writes the same bytes as before.

**Pre-build AC record (Step 2a):** frozen in `ac-record.jsonl`.

## Spec Impact
- **Classification:** none (how-only change under FR-01.11; reason `restores-specified-behavior`)
- FR-01.11 already promises ordered, uncorrupted per-run event files; this run makes the writer and readers keep that
  promise (one name rule, order across a rotation, no append to a torn file). No FR text changes, no new promise.

## Out of Scope
- Repairing a torn file. It stays as it is: when its last line is cut off (unreadable), F6 staging
  (`stage_event_drops.py` is all-or-nothing) and the run's absence gates keep refusing while it exists; a file that
  only lacks its final newline holds complete events and is staged as usual. AC3 stops the damage growing; a person
  removes the cut-off line while the file is untracked (`fold_events.py` handles it only after a merge). Said in the docs.
- A skewed clock on a shared implicit key (`_main`, `_branch-*`): the first event of a new file follows the newest
  event of that key, so one writer far ahead of real time pulls later events of the key forward with it (order and
  display only; no gate compares event `ts` to the wall clock). Accepted: a bounded bump would bring the tie back.
  An off-pattern non-ok drop reads with `key=None` and blocks every run's absence verdict (fail closed, intended).
- Events already moved to `shipwright_events.archive/` by a fold (older than 14 days) are not seen by the AC2 lookup.
- The adopt seeder's own copy of the name rule (ADR-045 keeps it separate); the seeder's CRLF append on Windows is a
  follow-up card. The scheduled fold. The "missing shipwright_events.jsonl" message wording.

## Behaviour change to note
A drop file whose name does not fit the writer's shape (leading dot, space, key over 80 characters) now reads with
`key=None` (it blocks every run's absence verdict while non-ok, as already the rule for `key=None`) and the staging
tool no longer stages it; the integrity check already refused such names. Writer-made names are unaffected (probed).

## Affected Boundaries
Producer/consumer pairs of the drop file name: `events_layout` (writer) -> `events_read`, `events_stage`,
`events_fold_io`, `events_integrity`, the F11 own-worktree test. Round trip: write a drop, read it, stage it, fold
it, check it (`integration-tests/test_events_drops_full_system.py` covers the chain; this run adds the shared-name
table test).

## Confidence Calibration
- **Boundaries touched:** the drop file name (six modules), the open-drop choice, the first-event timestamp.
- **Empirical probes run:** the rotation-order and torn-file tests failed before any fix; the CRLF item was probed
  through the existing tests and found already covered.
- **Test Completeness Ledger:** see the F5c entry.
- **Confidence-pattern check:** depth — each fix has a failing-first test; breadth — the name table test runs every
  module on a dozen names; integration — the existing drops integration suite runs unchanged.

## Internal Plan Review (opus-plan-reviewer)
- Ran: yes. Verdict: sound, narrowly scoped. Findings and what the plan does with them:
  - [medium] more name parsers than planned (`_own_worktree_drop` in the F11 verifier, the adopt seeder): the
    verifier uses `DROP_NAME` (AC1); the adopt copy stays out of scope (ADR-045), noted above.
  - [medium] AC2 only held inside one worktree and missed empty or folded files: the lookup goes by parsed KEY (wt8
    ignored) and also runs when the target exists but has no records; the archive gap is accepted and written down.
  - [medium] a torn own drop still blocks F6 and the absence gates: stated under Out of Scope, docs updated.
  - [low] the flat-load test is `test_events_read.py::test_the_reader_loads_standalone_by_path...`: extend it; the
    new definition stays INSIDE events_read (no new module).
  - [low] strictness is silent for staging: noted under Behaviour change. Per-write cost: fine.

## Architecture Review
- Internal (architecture-internal-reviewer): build it, with adjustments. Adopted: the name rule lives in
  `events_read.py` next to `sanitize_key` and is built from `KEY_MAX` (no new module, no flat-load wiring); `\Z`,
  never `$`; AC2 and AC3 cover every rotation and later writes reuse the one new file; torn means "does not end in a
  newline", whether or not the rest parses; keep the symlink condition; keep rotating, not repairing.
- External (glm, openai): both `revise`, no contradiction. Adopted: state the max+1 rule and test a frozen clock, an
  earlier clock and shuffled file names; torn = non-empty and last byte not a newline, so an empty file stays
  reusable; the lookup reads the valid records of a torn file without changing it (combined test: valid event, torn
  tail, new write); restrict the lookup to the drops layout and pin legacy bytes (AC4); the writer's key satisfies
  `DROP_NAME` (unit test).
