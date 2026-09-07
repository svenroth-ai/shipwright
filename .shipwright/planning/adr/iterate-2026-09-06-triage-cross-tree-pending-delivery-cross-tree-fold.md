# Fold sibling-worktree triage decisions into a main tree's own read

## Context

A decision (dismiss/promote/park/amend) recorded directly in a campaign or
iterate worktree's TRACKED `.shipwright/triage.jsonl` was invisible to any
other tree reading its own store: `triage.read_all_items` only ever unioned
ONE tree's own tracked + outbox files. An item dismissed only in a worktree
therefore read back on `main` as still open `triage`, with `pendingDelivery`
computing `False` — a false reassurance, the one direction an advisory marker
must never fail in. Measured live via `trg-5e0b9b16` / `trg-e85c5c8e`,
dismissed in `.worktrees/campaign-req3-04c-ac-identity-wave2` with
`by="cli"`, never routed through main's outbox.

## Decision

`triage.read_all_items`, when reading a MAIN tree (never a linked worktree —
detected from `.git` being a directory, not a file), also reads every
sibling's tracked `.shipwright/triage.jsonl` under `.worktrees/*` and folds
in any `status`/`amend` event for an id it already has an `append` for. Such
an item resolves to its decided status and is marked pending-delivery,
naming the branch that holds it (`originBranch` per row; `originBranches` as
two SEPARATE envelope-level maps in `list --json`, one for
`undeliveredDecisions` and one for `undeliveredAmends`, since a status and an
amend for the same id can each live on a different branch). Discovery is
filesystem-only — a linked worktree's `.git` file names its admin dir, whose
`HEAD` names the branch, both plain reads, no `git` subprocess — cached on
`(path, mtime)` for both the directory walk and the per-file parse. Nothing
is written anywhere by this fix: it changes what a read returns, never what
is on disk. New module `shared/scripts/lib/triage_cross_tree.py`.

## Consequences

`main` (and any main-tree reader: the board, the CLI, `pendingDelivery`) now
sees a sibling's already-decided item as decided, with the branch named, so
an operator is never told "still open" about a decision that has, in fact,
already been made elsewhere. The read cost is one directory walk plus one
parse per sibling per process (memoized within that process) — this repo
carries 84 sibling worktrees today, some logs exceeding a thousand records;
foreign records are filtered to `status`/`amend` only before caching, since
nothing downstream ever consumes a foreign `append`.

## Rationale

The boundary is "reported, never delivered": folding a foreign event into
another tree's read must not satisfy the origin-delivered GC rule (the event
still needs to reach the reading tree's OWN tracked store, or `origin`),
must never drop an outbox line, and must never be written into the reading
tree's tracked log. Only a sibling's TRACKED log is read, never its outbox —
that clone's own undecided buffer is not this tree's business. Only a MAIN
tree reads its siblings; a linked worktree never does, since it has no
`.worktrees` of its own in the normal layout — the reverse direction (a
worktree seeing a decision made on main, or on a peer) stays unaddressed by
design, matching the one direction the measured bug was actually in.

Two gaps were found by the Stage-3 doubt review and accepted rather than
fixed, since closing either would need exactly the mechanism the original
scope rejected: (1) **no expiry** — a sibling worktree whose branch was
merged or abandoned still reports its decision as pending forever, since
answering "is this branch merged" needs a `git` subprocess this module
deliberately avoids; an operator clears it by removing the worktree. (2)
**foreign corruption is stderr-only** — a corrupt span in a sibling's log
goes through the same `report_corruption` side channel as this tree's own
store, but `list --json`'s `corruption` block is built only from this tree's
own tracked + outbox, so a decision lost to corruption in a sibling has only
that stderr line as a signal; folding it in would touch the JSON contract
shape itself, out of scope for this change.

## Rejected alternatives

A delivery-receipt file written by the sweep (rejected by the original
mandate: this fix reports, it does not deliver — writing a receipt would
blur that boundary and create a second source of truth for delivery state).
A `git worktree list --porcelain` subprocess for discovery and branch
liveness (rejected: a subprocess call on every `read_all_items` invocation
is the wrong trade for facts — tree shape, checked-out branch — that never
change mid-process; it would also let this module answer "is this branch
merged", which is the no-expiry gap's actual fix, at the cost of a much
larger surface). A persistent cross-process cache (would amortize the
discovery/parse cost across a WebUI's repeated polls, but is out of scope:
this fix's cache is process-lifetime only, by design, mirroring every other
cache in this module).
