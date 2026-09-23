# Architecture Brief: m3-hook-parity-iterate-only

## The problem

A Codex-driven iterate is currently free to skip its own first mandatory
step (creating an isolated worktree) or to end its turn before mandatory
finalization has run, because nothing stops it beyond prose instructions in
a skill file it reads. When this happens, the operator has to notice and
manually restart or repair the session — a real, current annoyance, not a
hypothetical one.

## What already exists here

- A Codex plugin bundle that installs Shipwright's real hooks for Codex
  (merged from all 14 plugins' `hooks.json` files), built and verified
  deterministically.
- A best-effort Claude-side "repair pass" hook that runs at session end and
  tries to finish finalization if it looks incomplete — it never blocks or
  denies anything, it only tries to fix things up afterward.
- A read-only "is this phase done" checker used by a separate web dashboard
  to notice a stalled Codex session from the outside and nudge it.

## What would newly, permanently exist

Two small hook scripts that run automatically during a Codex-driven iterate:
one that refuses to let Codex's first action be anything other than the
required setup step, and one that, right before Codex's turn ends, checks
whether the mandatory wrap-up work happened — and if not, does that wrap-up
itself before allowing the turn to end (or refuses to end it if the wrap-up
genuinely can't be done). Both are inert for any session that isn't a
Codex-driven iterate that opted in. A small on/off switch controls whether
the second one is allowed to actually refuse to end a turn, defaulting to
off until it's been proven safe against a real Codex session.

## Options on the table

- **A:** Build both mechanisms now, scoped only to Codex and only to the
  iterate workflow, with the on/off switch above.
- **B:** Build only the "refuse the wrong first step" mechanism now; leave
  the "make sure wrap-up happened before ending" mechanism for later.
- **C:** Do nothing now — keep relying on the existing web-dashboard nudge
  mechanism plus prose instructions, and revisit only if this keeps
  happening.

## Constraints that are not negotiable

None.
