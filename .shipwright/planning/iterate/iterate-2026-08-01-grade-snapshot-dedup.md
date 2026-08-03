# Iterate: the grade log records changes, not heartbeats

- **Run ID:** `iterate-2026-08-01-grade-snapshot-dedup`
- **Date:** 2026-08-01
- **Status:** implemented
- **Intent:** CHANGE (Path B)
- **Complexity:** medium (Stage-1 `small` → escalated by the Stage-2 Repo Scout)
- **Anchor:** split out of trg-ac4fc684
- **Spec Impact:** NONE — no FR changes behavior. This changes the *cadence* of an
  internal producer, not a requirement. Justification recorded at F5c.

## Problem

`shipwright_events.jsonl` is a durable, git-tracked audit log. One event type
dominates it without carrying information.

Measured in this worktree on 2026-08-01 (the anchor's own numbers, re-measured —
the situation has grown worse, not better):

| Measure | Anchor (trg-ac4fc684) | Re-measured 2026-08-01 |
|---|---|---|
| Total lines | 587 | **695** |
| `grade_snapshot` lines | 172 (29%) | **234 (33.7%)** |
| Distinct `(grade, score)` values | 16 | 27 |
| Value transitions | 29 in 16 days | 52 in 20 days |
| Worst single day | 35 snapshots / 15 sessions | **47 snapshots / 20 sessions (2026-07-27)** |

On 2026-07-27 every one of those 47 snapshots carried the **identical** value
`('F', 49.0)`. One of them has an empty `session` field.

The emitter documents the no-dedup decision deliberately
(`_grade_snapshot.py`, AC1):

> Idempotency contract (AC1): exactly one snapshot per regen, appended
> UNCONDITIONALLY — no producer-side dedup. **A regen is an explicit act (a run
> finished)**; recording it every time keeps the producer trivial [...] while the
> WebUI dedupes consecutive identical (grade, score) points.

The premise in bold is what the measurement falsifies. A regen is not an explicit
act performed once per meaningful change — it fires on every compliance regen, in
every worktree, in every session. Twenty sessions in one day produced twenty
identical assertions that nothing had changed. Delegating dedup to the WebUI is a
sound division of labour for *rendering*, but it does not stop the durable log —
which is committed, merged, reviewed and diffed — from being one-third heartbeat.

The decision was reasonable when written. It rested on a claim about the world
("a regen is an explicit act") that could only be checked by measuring, and the
measurement now exists.

## Approach

Suppress an append when it would record **the same grade, from the same kind of
tree, as the most recent preceding snapshot**. Do the check inside the same file
lock as the append.

### Choosing the dedup key — measured, and the first answer was wrong

The comparator is the most recent `grade_snapshot` **in append order, ignoring
intervening event types** — not the last line of the log.

Two rules govern which snapshots are comparable at all:

- **Attribution must be resolvable on both sides.** A record whose `lineage` is
  absent (every snapshot written before attribution existed — 192 of the 234) or
  `"unknown"` (the resolver degraded) is never treated as the same tree as
  anything. Two records that cannot be attributed are not thereby equal.
- **The tree identity is the `lineage` class** (`main` / `branch`), not the branch
  name.

The second rule is a correction. The first draft of this plan keyed on
`(lineage, branch)`, and simulation appeared to endorse it at a 71% reduction. That
number was an artifact: the simulation compared `lineage` with `.get()` defaults, so
all 192 attribution-less historical records collapsed into one pseudo-tree and
deduped against each other. External plan review (openai, edge-case/medium) flagged
exactly that hazard. Re-measured with the attribution guard in place, the picture
inverts:

| Key | Going-forward regime (42 attributed) | 2026-07-27 replay (20 branches, one value) |
|---|---|---|
| `(lineage, branch)` | 42 → 37 (12%) | **20 → 20 — fixes nothing** |
| **`lineage` class** | **42 → 23 (45%)** | **20 → 1** |
| value only, any tree | 42 → 23 (45%) | 20 → 1 |

Keying on the branch name cannot fix this problem, because *the problem is
cross-branch*: 20 sessions on 2026-07-27 meant 20 different worktrees, so a
same-branch key finds no predecessor to compare against and every one of them
appends. A key that leaves the measured defect at 100% is not a conservative
choice; it is a no-op with extra steps.

Between the two keys that do work, **`lineage`-class is chosen over value-only**
because it is strictly safer at identical effectiveness: value-only lets a branch
snapshot suppress a `main` snapshot carrying the same number, so a consumer
filtering `lineage == "main"` loses that point. Restricting the comparison to a
matching class makes that impossible by construction, and today's data cannot tell
the two keys apart (there are no `main`-lineage snapshots yet), so the safer rule
costs nothing.

**What this key gives up, stated plainly:** a per-*branch* view can lose a point —
if branch X's only snapshot repeats the value an unrelated branch logged just
before it, X's snapshot is suppressed. That is accepted. `lineage` is what the
attribution iterate documented consumers filter on; `branch` is descriptive
metadata on a point, not a series selector, and a 1-2 point per-branch series is
not a trend. The audit question "did a compliance regen run for branch X" is
answered by that run's `work_completed` event (430 of them in this log), not by a
duplicate grade assertion.

Verified against the corrected rule: the whole-series value path and every
`lineage`-class value path are preserved; a real transition appearing mid-run is
never swallowed; a `main` point is never suppressed by a branch point; two
`unknown`-lineage records never dedup.

### Where the code goes

`record_event.append_event_idempotent` already solves the hard half of this
problem: it performs the dedup scan and the append **inside one `_FileLock`**,
precisely so two concurrent writers cannot both pass the scan before either
append lands. That lesson was learned the expensive way for `phase_completed`
(deep-audit F14). The new rule becomes a branch there, reusing the proven
concurrency shape rather than inventing a second one, and keeping the emitter's
own change to a few lines.

It is **opt-in** (`deduplicate_grade_snapshot=False` by default), mirroring the
existing `deduplicate_by_commit` flag. Only the compliance emitter passes it —
an earlier draft applied it to both producers, which the external plan review
correctly flagged as silently changing replay/backfill semantics (AC5).

The rule itself lives in **`shared/scripts/lib/event_dedup.py`**, not inline.
Two reasons, one of them forced: `record_event.py` is an ADR-111 size exception
pinned at 769 lines by the bloat baseline, and inlining put it at 878 — the
anti-ratchet pre-commit hook blocks that, correctly. The file's own precedent
(`lib/fr_gates.py`) is to move a cohesive rule out rather than ratchet the
exception larger, so the pre-existing `has_commit` / `has_phase_event`
predicates moved with it: one module now owns *"when is an append a duplicate"*,
and `record_event.py` ends at **757** — 12 lines smaller than before this change
added a feature. All three predicates are re-exported under their historical
names, so every call site and monkeypatching test resolves unchanged.

### What is explicitly NOT done

**The existing 234 lines are not compacted.** `compliance_input_state.py` states
the rule in its own words — *"never destroy an appended line"* — after an earlier
attempt at rewinding this log had its guard exactly backwards and destroyed a
concurrent writer's append. Rewriting history in a durable audit log to make a
chart tidier is not a trade worth making. The fix is going-forward only; the
historical noise stays and is honest about what the producer used to do.

## Acceptance Criteria

- [x] **AC1** — A regen whose grade/score match the most recent preceding
  `grade_snapshot` **of its own `lineage` class** appends nothing, and reports
  `{"appended": 0, "reason": "unchanged_grade", "grade": ..., "score": ...}`.
  **Where each half of that contract lives:** `append_event_idempotent` keeps its
  established `(event_id | None, skip | None)` tuple and returns
  `skip = {"reason": "unchanged_grade", "grade": ..., "score": ...}`; the emitter
  adds `appended: 0`, exactly as it already does for its `not_gradeable` skip. The
  `appended` key is emitter vocabulary, not helper vocabulary — the helper has no
  such key today and gaining one would change the shape its existing caller
  renders.
- [x] **AC1b** — The new branch is gated on the opt-in flag **and** on
  `event["type"] == "grade_snapshot"`, so enabling the flag for another event type
  cannot silently apply grade semantics to it.
- [x] **AC2** — A regen whose grade **or** score differs appends normally.
- [x] **AC3** — A regen whose value matches but whose `lineage` class differs appends
  normally, so a `lineage`-filtered consumer keeps every transition it had before.
- [x] **AC3b** — A snapshot is never suppressed when either side's attribution is
  unresolvable. Resolvable means `lineage` is a string in the **closed set
  `{"main", "branch"}`** — `null`, `""`, `"unknown"`, `"MAIN"` and any other value
  are non-comparable. Sameness of tree is established, never assumed, and "both
  sides carry the same invalid value" does not establish it.
- [x] **AC3c** — The comparator is the most recent preceding `grade_snapshot`
  **of the same `lineage` class** (a reverse scan filtered by class), not the
  absolute last snapshot. Intervening events — of other types *or of the other
  lineage class* — do not defeat deduplication. Scanning only the absolute last
  snapshot would make an alternating `main`/`branch`/`main` sequence dedup
  nothing at all, since every record would find a predecessor of the other class;
  verified 4 → 4 with the absolute-last comparator vs 4 → 2 with this one. Each
  lineage class is its own series, which is also what makes AC3 fall out by
  construction rather than needing a special case.
- [x] **AC3d** — The comparison **never raises**. A candidate is *non-comparable* →
  append, unless `grade` is a non-empty `str` **and** `score` is an `int`/`float`
  that is **not a `bool`** and is **finite**. Both reviewers independently flagged
  that a naive `float(event["score"])` over durable, union-merged, amendable data
  would raise **inside the lock**; for the emitter that lands in
  `update_compliance`'s best-effort wrapper and the snapshot is **lost**, which is
  strictly worse than the duplicate this change exists to remove. Reachable in
  practice: `read_events` recovers malformed *lines* but not valid JSON with an
  invalid payload, and `event_amended --fields` blocks only the attribution keys,
  so an amendment may set `score` to a string. `bool` is excluded explicitly
  because `float(True) == 1.0` would otherwise read as a grade of 1.0; numeric
  strings like `"95"` are malformed, not coerced, because the wire shape is
  numeric. Equality is on `(grade, float(score))`, so an int `95` and a float
  `95.0` compare equal.
- [x] **AC3e** — The predecessor is read from the **effective** history after
  `event_amended` overlays. A snapshot corrected from B/88 to A/90 therefore
  cannot suppress a later B/88 transition. Malformed amendments fail open and
  append, just like malformed snapshots and corrupt JSONL fragments.
- [x] **AC4** — The dedup decision and the append happen inside **one** `_FileLock`
  acquisition. **Scope, stated honestly: this serialises writers against one
  checkout's log file, and that is the whole of the guarantee.**
  `resolve_events_path` is a literal per-tree join, so two worktrees hold two files
  and two locks. Duplicates therefore survive in two situations, not one:
  *concurrent* regens in separate worktrees, and — more commonly — a **stale**
  worktree whose checked-out log predates a snapshot merged elsewhere, which will
  append a value already recorded on `main`. The bound is "one line per tree whose
  log did not yet contain the value", **not** "one per concurrent worktree" (an
  earlier draft of this AC claimed the narrower bound and was wrong).
  What makes the fix effective anyway is that iterate worktrees are created off a
  freshly-fetched `origin/<default>` (`setup_iterate_worktree`) and refreshed by
  `ensure_current` before the arm, so a tree's log is current at the moments that
  matter. Eliminating the residual entirely would need one authoritative log
  location and a shared lock; explicitly out of scope. The stale-tree behaviour is
  **pinned by a test** so it reads as a known limit rather than an assumption.
- [x] **AC5** — The `record_event.py --type grade_snapshot` CLI **keeps its current
  unconditional-append behaviour.** Dedup is opt-in via a
  `deduplicate_grade_snapshot` parameter on `append_event_idempotent` (mirroring
  the existing `deduplicate_by_commit` flag), which only the compliance emitter
  passes. This is not a hedge: `grade_snapshot_shape.py` and
  `docs/hooks-and-pipeline.md` both define that CLI as the **manual/replay** route,
  and the premise this iterate falsifies — *"a regen is an explicit act"* — is
  false for an automatic regen and **true** for a hand-run replay. Dedup belongs
  exactly where the premise fails. Defaulting the flag off also means no existing
  caller's result contract changes.
- [x] **AC6** — The documented contract is corrected everywhere it is asserted:
  `_grade_snapshot.py`'s module docstring, `test_grade_snapshot_regen.py`'s AC1
  test, and `compliance_input_state.py`'s two "appends one grade_snapshot per run"
  comments.
- [x] **AC7** (incidental, in-path) — `lib/config.read_events`' docstring claims it
  "resolves the canonical (main-repo) event log ... rather than an absent/empty
  worktree-local copy". That is false: `resolve_events_path` was changed to a
  literal per-tree join and the claim was left behind. The dedup read goes through
  this function, and the stale claim actively misled the external plan review's
  model of the concurrency scope. Corrected in the same diff.

## Affected Boundaries

- `shipwright_events.jsonl` — durable, git-tracked, union-merged across worktrees,
  read cross-repo by the WebUI Ship's-Log.
- `append_event_idempotent`'s lock discipline (concurrent writers, one checkout).
- The `grade_snapshot` wire shape — **unchanged**; only cadence changes.
- `append_event_idempotent`'s skip contract. Verified: it has exactly **one**
  caller today (the `record_event` CLI at line 755), plus the emitter this iterate
  adds — so the new branch's blast radius is enumerated, not assumed.

## Confidence Calibration

- **Boundaries touched:** the durable event log (append + read-back under lock);
  the compliance regen's best-effort result payload; the `record_event` CLI's
  `skipped` output contract. Wire shape untouched.
- **Empirical probes run:**
  - Re-measured the live log: 234/695 snapshots (33.7%), 27 distinct values, 52
    transitions, worst day 47 snapshots from 20 sessions all identical — the
    anchor's premise falsified on current data, not remembered data.
  - Simulated candidate dedup keys over the real snapshots. **The first probe was
    measuring the wrong thing** — it compared attribution with `.get()` defaults,
    so 192 attribution-less records read as one tree and reported a 71% win for a
    `(lineage, branch)` key. Re-running with the attribution guard showed that key
    suppresses **nothing** on the actual defect (20 → 20 on a 2026-07-27 replay),
    because the defect is cross-branch. The plan changed as a result.
  - Probed the corrected rule against each way it could be wrong: real transition
    mid-run (survives), branch-then-main same value (main survives),
    two unknown-lineage records (never dedup), whole-series and per-class value
    paths (both preserved), 2026-07-27 replay (20 → 1).
  - Read `resolve_events_path`: a literal per-tree join. This **falsifies** the
    "one lock covers all producers" reading — each worktree has its own file and
    its own lock — and also falsifies `read_events`' own docstring (AC7). AC4 is
    scoped to one checkout as a result.
  - Confirmed `append_event_idempotent` already holds scan+append in one lock, so
    the intra-checkout half of AC4 is inherited rather than re-implemented.
  - Enumerated callers of `append_event_idempotent`: exactly one today (the CLI),
    so the new branch's blast radius is known rather than assumed.
  - **Mutation-tested the three guards the "never raises" contract rests on.**
    Two of them (`bool`, `isfinite`) survived deletion with a fully green
    suite, because every malformed-score case was ASYMMETRIC and so never
    reached the equality the guards prevent. Symmetric cases were added and the
    mutants now die. The read guard was falsified the same way. This is the one
    place where "the tests pass" was measurably not evidence.
  - Confirmed `change_history.collect_events` filters `grade_snapshot` out, so the
    convergence checker in `compliance_input_state` gets *more* convergent, not
    less: pass 1 appends, pass 2 sees an identical value and skips.
- **Test Completeness Ledger:** see below.
- **Confidence-pattern check:**
  - *Asymptote (depth)* — the risky decision was the dedup key. Probing it did not
    asymptote on the first pass: the second measurement reversed the first and
    changed the design. It asymptotes now — the corrected rule was tested against
    five distinct falsification attempts and none moved it.
  - *Coverage (breadth)* — both producers (emitter + CLI), both outcomes
    (append/skip), attribution-differs, attribution-unresolvable, intervening
    event types, and the concurrency invariant each have a test. Deliberately
    uncovered: historical compaction (not done) and the cross-worktree residual
    (out of scope, documented in AC4 rather than silently omitted).
  - *Integration composition* — `cross_component` does not fire on this diff
    (verified against `CROSS_COMPONENT_FILE_PATTERNS`); the existing
    `TestComplianceRegenComposition` real-flow test is extended to cover the
    second regen, so the emitter and the compliance loop are proven to compose
    under the new contract rather than only in isolation.

## Test Completeness Ledger

Test module keys: **D** = `shared/tests/test_grade_snapshot_dedup.py`,
**N** = `shared/tests/test_grade_snapshot_dedup_never_raises.py`,
**R** = `plugins/shipwright-compliance/tests/test_grade_snapshot_regen.py`.

| # | Behavior | Status | Evidence / reason |
|---|---|---|---|
| 1 | Identical consecutive snapshot, same lineage class, is suppressed (AC1) | `tested` | D `test_an_unchanged_grade_is_suppressed` |
| 2 | Changed grade or score appends (AC2) | `tested` | D `test_a_changed_grade_or_score_appends` |
| 3 | Same value, different lineage class, appends (AC3) | `tested` | D `test_the_same_value_from_a_different_lineage_class_appends` |
| 4 | Attribution outside `{main, branch}` (absent / null / `""` / `unknown` / `MAIN` / non-string) never suppresses (AC3b) | `tested` | D `test_an_unresolvable_lineage_is_never_comparable` |
| 5 | Intervening events of other types do not defeat dedup (AC3c) | `tested` | D `test_intervening_events_of_other_types_do_not_defeat_dedup` |
| 5b | Intervening events of the other lineage class do not defeat dedup (AC3c) | `tested` | D `test_alternating_lineage_classes_still_dedup` |
| 5c | A real transition is never swallowed (AC2) | `tested` | D `test_a_real_transition_is_never_swallowed` |
| 5d | The new branch is gated on event type as well as the flag (AC1b) | `tested` | D `test_the_flag_does_not_apply_grade_semantics_to_other_types` |
| 6 | Helper skip payload is exactly `{reason, grade, score}` — no `appended` (AC1) | `tested` | D `test_an_unchanged_grade_is_suppressed` (asserts the dict by equality) |
| 6b | Emitter adds `appended: 0` on top of it (AC1) | `tested` | R `test_a_regen_that_changes_nothing_appends_nothing` |
| 7 | Scan + append share one lock acquisition (AC4) | `tested` | D `test_the_dedup_scan_and_the_append_share_one_lock` — injects a competing write on lock entry, the `_InjectingLock` pattern from `test_record_event_lifecycle_integrity` |
| 8 | Replay route still appends an identical snapshot — dedup is opt-in (AC5) | `tested` | D `test_the_replay_route_still_appends_an_identical_snapshot` |
| 9 | The other dedup branches are unaffected (AC5) | `tested` | D `test_other_dedup_branches_are_unaffected` |
| 10 | First snapshot into an empty log appends | `tested` | D `test_the_first_snapshot_in_an_empty_log_appends` |
| 11 | Compliance regen composes end-to-end under the new contract | `tested` | R `TestComplianceRegenComposition::test_a_second_regen_over_unchanged_data_adds_nothing` (drives `update_compliance.main` twice) |
| 12 | Not-gradeable still skips with `reason:"not_gradeable"` (unchanged) | `tested` | R `test_not_gradeable_repo_emits_nothing` (existing, still green) |
| 13 | Int and float score representations compare equal | `tested` | D `test_an_int_and_a_float_score_are_the_same_score` |
| 13b | Malformed predecessor score never raises and never suppresses (AC3d) | `tested` | N `test_a_malformed_predecessor_score_never_raises_and_never_suppresses` |
| 13c | Malformed candidate score never raises and never suppresses (AC3d) | `tested` | N `test_a_malformed_candidate_score_never_raises_and_never_suppresses` |
| 13d | Malformed grade never raises and never suppresses (AC3d) | `tested` | N `test_a_malformed_grade_never_raises_and_never_suppresses` |
| 13e | Two unreadable records are not equal to each other — no `None == None` suppression (AC3d) | `tested` | N `test_two_malformed_records_are_not_equal_to_each_other`, parametrized SYMMETRICALLY over null/`True`/±inf/numeric-string/overflowing-int. **Mutation-verified**: deleting the `bool` guard fails `[true]`, deleting the `isfinite` guard fails `[inf]` and `[-inf]`. Before these were symmetric, both guards survived deletion with the whole suite green (Stage-3 doubt review) |
| 13e2 | A corrupt log LINE never suppresses or costs the snapshot (AC3d) | `tested` | N `test_a_corrupt_line_never_turns_an_older_match_into_a_skip` under default warning handling and `test_a_corrupt_line_warning_as_error_does_not_cost_the_snapshot` under `warnings.simplefilter("error")`; corruption is an explicit reader result, so an unreadable intervening fragment fails open regardless of warning policy |
| 13e3 | Numeric subclasses whose `__float__` raises never cost the snapshot (AC3d) | `tested` | N `test_a_numeric_subclass_conversion_failure_never_raises`, parametrized over `TypeError` / `ValueError` / `OverflowError` |
| 13e4 | Non-object entries handed to the public comparison helper never raise or shield an earlier comparable snapshot (AC3d) | `tested` | N `test_a_non_object_entry_handed_to_the_helper_never_raises` |
| 13e5 | Effective amended history preserves real transitions and malformed amendments fail open (AC3e) | `tested` | N `test_an_amended_predecessor_preserves_the_effective_transition`, `test_a_malformed_amendment_fails_open` |
| 13f | A stale tree appends a value already recorded elsewhere (AC4 limit) | `tested` | D `test_a_stale_tree_still_appends_a_value_recorded_elsewhere` |
| 13g | The scan reads the events it is handed, not a re-resolved path (AC4) | `tested` | D `test_last_grade_snapshot_reads_the_events_it_is_given` |
| 13h | Historical `record_event.read_events` monkeypatch seam remains effective after predicate extraction | `tested` | D `test_record_event_reader_monkeypatch_seam_is_preserved` |
| 14 | Historical 234 lines are left intact | `untestable` | `covered-by-existing-test` — the change adds no compaction path; `compliance_input_state`'s append-only rewind rule is already pinned by its own suite |

Zero testable-but-untested behaviors.

The cross-worktree residual in AC4 is deliberately **not** a ledger row: it is the
absence of a guarantee this change never claimed, not a behavior the diff
introduces, and none of the closed-vocabulary `reason_code` values would describe
it honestly. It is documented where it belongs — in AC4.

## Assumptions (recorded because `--autonomous` skipped the interview)

1. **Going-forward only, no history compaction.** Justified above; reversing this
   would mean rewriting a durable audit log.
2. **Dedup keys on tree attribution, not on session.** A session id says who ran
   the regen; the grade is a property of a tree. Keying on session would fail to
   suppress the exact 2026-07-27 pattern (20 sessions, one value).
3. **The WebUI keeps its own dedup.** It is now redundant for consecutive
   identical points but remains correct, and removing it is a change in another
   repo that this iterate has no business making.
