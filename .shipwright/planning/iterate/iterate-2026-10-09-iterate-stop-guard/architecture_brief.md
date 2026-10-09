# Architecture Brief: iterate-stop-guard

## The problem
An autonomous change run (the operator hands off a task and expects a merged result) regularly ends its turn right after the build and asks the operator how to continue, skipping review and finalization. Nothing in the system prevents it; the only Stop hook for iterate is a repair pass that never blocks.

## What already exists here
- `iterate_stop_finalize.py`: Stop hook, repair pass, always exits 0.
- Run pointer per session, written at worktree setup, deleted when delivery reaches MERGED/CLOSED.
- `bloat_gate_on_stop.py`: an existing Stop hook that blocks with `decision: block`.
- Written rules in `SKILL.md` (no rule about stopping).

## What would newly, permanently exist
A Stop hook that blocks while an autonomous run is open, a small state file per run (block counters, recorded blocker), and a CLI to record an unresolvable blocker. The maintainers keep the hook's heuristics (autonomous detection from the transcript, counters) correct.

## Options on the table
- **A:** Stop hook blocking while the run pointer is live and the session is autonomous.
- **B:** Only strengthen the written rules in `SKILL.md` and add a task checklist.
- **C:** Stop hook that asks GitHub whether the PR is merged.
- **D:** Do nothing.

## Constraints that are not negotiable
Interactive iterates must still be allowed to ask questions; a failing guard must never trap a session.
