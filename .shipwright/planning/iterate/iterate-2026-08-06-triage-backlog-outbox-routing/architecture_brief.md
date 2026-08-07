# Architecture Brief: triage-backlog-outbox-routing

## The problem

A background producer (the compliance-backlog Stop hook) writes to the
tracked `.shipwright/triage.jsonl` throughout the lifetime of an iterate
run. When the run's finalization step tries to merge the latest shared
branch into the iterate branch, it sometimes finds that file uncommitted
at exactly the wrong moment and refuses to proceed — the merge aborts
outright rather than starting. This has happened at least twice within a
single run and on a separate pull request across two consecutive
attempts, forcing the operator to manually fold the pending writes into a
commit each time before the run could continue.

## What already exists here

- A dedicated conflict resolver already exists for this exact file — it
  treats it as an append-only log and reconciles divergent additions from
  both sides of a merge, rather than picking one side.
- A separate mechanism already exists for carrying a DIFFERENT small class
  of run-owned files (test-evidence and session-handoff notes) across this
  same merge step, by holding their bytes in memory and writing them back
  after the merge completes.
- A gitignored, per-tree buffer already exists that some OTHER background
  producers write to instead of the tracked log, specifically so an idle
  clone's tracked log never accumulates uncommitted background writes.

## What would newly, permanently exist

A small conditional step inside the existing pre-merge guard: immediately
before that guard attempts the merge, it checks whether the tracked
triage log is dirty and, if so, folds it into its own small commit first.
Nothing new is scheduled, no new credential or service is introduced, and
no new file location is created — it is one additional check inside a
guard that already runs on this path for every iterate finalization, and
it produces an ordinary commit indistinguishable in kind from ones a
human already makes by hand today when this happens.

## Options on the table

- **A:** Fold the uncommitted triage log into its own commit immediately
  before the merge guard attempts to merge.
- **B:** Change the background producer so its writes never land in the
  tracked log while an iterate run is in progress, only in the gitignored
  per-tree buffer.
- **C:** Extend the existing carry-in-memory mechanism (used today for
  two other run-owned files) to cover the triage log as a third member.
- **D:** Do nothing further — continue relying on the operator to notice
  and manually commit the file when the merge refuses.

## Constraints that are not negotiable

none
