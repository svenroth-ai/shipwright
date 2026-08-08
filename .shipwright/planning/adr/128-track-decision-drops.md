# ADR-128 — Track decision-drops in git; redirect the write path into the calling worktree

**Run-ID:** iterate-2026-08-08-track-decision-drops
**Date:** 2026-08-08
**Supersedes:** ADR-050 (decision-drops gitignored by design)
**Revises a load-bearing premise of:** ADR-127 (decision-log and decision-drops
indexes) — that ADR assumed the drops directory was disk state local to one
machine; this ADR makes it tracked, shared history instead.

## Context

`.shipwright/agent_docs/decision-drops/` is the per-iterate staging area for
ADR content before `/shipwright-changelog` aggregates it into
`decision_log.md` at release. ADR-050 gitignored the directory on the
reasoning that it is transient, single-machine scratch state consumed by the
very next release. In practice it accumulated 214 real decision drops on one
operator's machine, entirely invisible to CI, to any second checkout, and to
any other operator or worktree — undiscovered because nothing ever failed
loudly; the drops simply never shipped into `decision_log.md` on any other
machine's clock.

Worse, the write path itself pointed at the **main repo's disk**, not the
calling iterate's own worktree — an iterate running in
`.worktrees/<slug>/` was writing decision-drops into
`C:\...\shipwright\.shipwright\agent_docs\decision-drops\`, the main
checkout, not its own tree. A gitignored directory outside the worktree
being written to is invisible by two independent mechanisms at once.

## Decision

Track `.shipwright/agent_docs/decision-drops/` in git, in three places:
this repo's `.gitignore`, the shared `shipwright-gitignore.template`
consumed by every project `shipwright-adopt` onboards, and the separate
`shipwright-webui` repo's own `.gitignore`. Redirect the write path
(`write_decision_drop.py`) from the main repo's disk to
`{project_root}` — which for an iterate run is the calling worktree,
so a drop lands inside the branch that will carry it, not a sibling
checkout.

Add a legacy-drop quarantine (`lib/decision_drop_legacy.py`): a drop whose
**file** predates the tracking cutoff (`2026-08-08`, read from filesystem
mtime, never the JSON `date` field — that field is a legitimately
backdatable narrative date for the rendered `decision_log.md` entry,
orthogonal to the file's own provenance) is moved, never deleted, into a
gitignored `decision-drops-legacy-pending-scan/` sibling. None of the 214
pre-existing drops have ever been gitleaks- or prompt-scanned, so silently
aggregating them into a tracked commit on first contact would ship
unscanned content; quarantining forces an explicit, scanned backfill
instead.

F6's staging line for `decision-drops/` is glob-scoped to
`{run_id}_*.json` rather than the whole directory. Every other F6
directory-level `git add` is already run-scoped by directory structure
(e.g. `planning/iterate/<run_id>/`); `decision-drops/` is uniquely a flat
directory shared across a campaign's branch-hopping sub-iterates, so a
directory-wide add would sweep in an unrelated sibling iterate's
in-flight drop.

## Consequences

Decision-drops become ordinary tracked, mergeable state: visible in `git
status`, reviewable in a diff, present in any checkout. A drop written in
one worktree ships with that worktree's branch instead of silently
depending on which machine happens to run `/shipwright-changelog` next.
The legacy quarantine adds one more gitignored directory and one more
explicit backfill step for the 214 pre-existing drops, deferred to a
follow-up run (this run is PR 1 of 2 per the internal Opus plan review).
`decision_log_gate.py`'s `resolve_main_repo_root` redirect is removed
entirely — a drop now resolves directly against `project_root` with no
main-checkout fallback, simplifying the verifier and closing the
worktree-invisibility gap it existed to work around.

## Rationale

The alternative of merely *fixing the write path* (worktree-local writes)
without also tracking the directory in git would still leave every
existing operator's drops gitignored — invisible to CI and any second
checkout, just no longer also misdirected to the wrong disk. Both defects
share one root cause (the directory was never meant to be durable,
shared state, and now is), so both are fixed together rather than
sequentially risking a second silent-loss window between fixes.

## Rejected alternatives

1. **Commit the 214 pre-existing drops directly, unscanned.** Rejected:
   they have never been gitleaks- or prompt-scanned; committing them
   without that gate is exactly the silent-content-risk this framework's
   own security tooling exists to catch.
2. **Bump ADR-127's numbering scheme instead of adding a new ADR.**
   Rejected: ADR-127 is about index generation; this change is about
   directory tracking and write-path resolution — a distinct decision
   with its own consequences, not a footnote on an unrelated ADR.
3. **Track the directory but leave the write path pointed at the main
   repo's disk.** Rejected: a worktree-run iterate would still write
   outside its own branch, so the drop would never appear in that
   iterate's diff or PR at all — tracking alone does not fix the
   invisibility.
