# Iterate Spec: events-fold-at-release

- **Run ID:** iterate-2026-11-11-events-fold-at-release
- **Type:** change
- **Complexity:** medium (classifier said small; raised because the change adds an automatic commit to the release path)
- **Status:** draft

## Goal
Old per-run event files (`shipwright_events.d/`) are folded into `shipwright_events.archive/` automatically at
each release, in a commit of their own, so nobody has to remember the housekeeping (the open-file count stays low
as long as releases happen; a bound between releases is the later warning iterate). The target audience does not care about this; it is compliance
housekeeping, so it must run in the background and must never stop a release.

## Decision (from the operator, 2026-11-11)
Fold at release (option "release step"), not a scheduled CI job (the product ships little CI and keeps it optional).
A warning when the open count nears ~150 is a separate, later iterate.

## Findings (checked against the code)
1. `tools/fold_events.py fold` already does the right move (merged on the base ref, unchanged, every event older
   than 14 days; one archive; `.keep` stays) but a person has to run it, stage it and commit it.
2. `/shipwright-changelog` is the one serialized, single-actor point of a release (version, changelog, ADR numbers),
   which is what the docs ask for ("folds are single-actor release work"). A live run is safe: its drop is not on the
   base ref yet and its events are younger than 14 days.
3. The release commit is made by explicit pathspec, and `git commit -- <paths>` ignores whatever else is staged; a
   thousand drop names overflow a Windows command line, so the paths go in on stdin (`--pathspec-from-file`).

## Acceptance Criteria
- [ ] AC1 When a release is cut in a project that uses per-run event files, event files that are already merged and
  older than two weeks are folded into the archive in a commit of their own, before the release commit, and no event
  is lost or duplicated.
- [ ] AC2 Whatever else is staged for the release stays out of that fold commit, and an event file of a run still in
  flight is left alone.
- [ ] AC3 A release never stops because of the fold: a conflicting id, an unresolvable base, a file that cannot be
  deleted or a refusing commit hook each end in one printed line and the release goes on. A project on the single
  event log, and a second run with nothing left to fold, change nothing.

**Pre-build AC record (Step 2a):** frozen in `ac-record.jsonl`.

## Spec Impact
- **Classification:** none (reason `tooling-only`): release tooling that runs housekeeping the docs already ask for
  ("fold now and then, as single-actor release work"). No FR text changes, no new promise to a user.

## Out of Scope
- A warning when the open count nears ~150 in `main_health` / F0 (next iterate).
- A scheduled GitHub workflow (optional extra, not built).
- Folding inside an iterate, or on a feature branch.
- Archived events and the ordering lookup (unchanged, see events-writer-hardening-2).

## Behaviour to note
A failed fold puts the tree back as it was and the release goes on; the next release tries again. What counts as
merged is the repo's own trunk (`origin/HEAD`). A file with local changes is skipped. A merged drop is never appended
to again (the writer opens a new file once HEAD holds the old one), so a fold cannot collide with a branch that
keeps writing it. The fold commit stays its own commit only when the release is merged without squashing. The
release now contains one more commit, `chore(events): fold N event files older than 14 days into the archive`,
when there is anything to fold. The tag stays on the release commit.

## Affected Boundaries
Producer/consumer: `fold_events_for_release.py` -> `tools/fold_events.py` (`_stage`, `_stage_paths`, now `_stage`
returns the staged paths) -> `lib/events_fold`. The changelog skill reads only the JSON `status`. The integrity check
(F11, `check_events_integrity`) already accepts a fold commit.

## Confidence Calibration
- **Boundaries touched:** the release path (new commit), the fold tool's staging helper.
- **Empirical probes run:** 11 tests on real git repos (own commit, other staged work, in-flight run, legacy layout,
  conflict, missing base, undeletable file, refusing hook, 900 files, CLI). A rename-detection pitfall in `git show`
  was found and handled in the test (git shows the deleted drop and the identical archive as a rename).
- **Confidence-pattern check:** depth: each failure mode has a test; breadth: the existing fold suite runs unchanged.

## Internal Plan Review (opus-plan-reviewer)
- Ran: yes. Verdict: core sound; the failure path was not. Findings and what the plan does with them:
  - [high] a refused commit left the fold staged and Step 7's event commit would then commit the deletions without the
    archive: every failure after the fold started now puts the tree back (`rolled_back`), tested (clean `git status`,
    other staged work kept, half-deleted fold, hook refusal, hooks never bypassed).
  - [medium] exceptions after the fold were reported as "nothing changed": they now run the same rollback.
  - [medium] autonomous Step 5 jumped to Step 6: now says "continue with 5.3, 5.4, 5.5, 6".
  - [medium] base fixed to `origin/main`: default is now `origin/HEAD`, else `origin/main`, else `origin/master`.
  - [medium] modify/delete with branches still writing a merged drop: cannot happen, the writer opens a new file once
    HEAD holds the old one (stated in Behaviour to note).
  - [low] squash merge keeps one commit (noted); commit timeout/hook stall (handled as `commit_failed` + rollback,
    git 2.25 stated); step order before 5.5 (stated in the skill).

## Internal Architecture Review (architecture-internal-reviewer)
- Ran: yes. Verdict: build with adjustments (option A: smallest option that fixes it). Adopted: failure paths restore the
  tree; hooks are never bypassed (tested); the one printed line carries `open_files`; the open-count warning iterate is
  the required detection half. Not adopted: making it a mode of `fold_events.py` (that tool is a documented four-mode
  CLI; the wrapper reuses it and `_stage` now returns the staged paths, its only other caller ignores the value).

## Architecture Review
- External (glm, openai): both `approve`. Reconciliation: reword the goal (release-triggered, best-effort: no promise of a
  hard ceiling between releases) - done; keep the warning iterate scheduled - recorded as the next iterate.
- External plan review (glm, openai): both `revise`, no contradiction. Adopted: rollback on every failure, a dirty-file
  check (a file with local changes is skipped), tests for both. Not adopted: a branch check (a release PR may carry the
  fold) and a "live run" guard beyond merged + unchanged + older than 14 days (a merged drop is never appended to).

## Doubt Review (doubt-reviewer, opus) - answers
- [medium] a revert of a merged release fails the integrity gate (the archive exists at the merge-base): documented in
  Step 5.3 and `docs/hooks-and-pipeline.md` (revert only `chore(release)`, never the `chore(events)` fold commit).
- [medium] a rollback that half-fails deleted the archive: fixed. The archive this run wrote is removed only after every
  tracked drop is confirmed back; otherwise `rolled_back: false` and it stays (test). The repair for `rolled_back: false`
  and a left-behind `index.lock` is written into Step 5.3 and the docs.
- [low] the plan used the trunk tip, the integrity check the merge-base: fixed, the fold plans against
  `git merge-base <trunk> HEAD` (test with a squash-merged drop).
- [low] an aborted release leaves the fold commit, which could read as a release note: rebutted, the release notes are
  rendered from the changelog drop files (Step 4), not from commit subjects; stated in Step 5.3.
