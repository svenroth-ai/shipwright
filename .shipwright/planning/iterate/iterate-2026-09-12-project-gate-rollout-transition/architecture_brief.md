# Architecture Brief: project-gate-rollout-transition

## The problem

Two `/shipwright-project` Step-8 gates (`check_criteria_free_of_implementation_detail`,
`check_no_empty_split`) were added recently as unconditional hard blocks with
no carve-out for a project that already existed before the gates did. An
`/shipwright-adopt`-onboarded (extension-scope) project can have `spec.md`
content written long before these gates existed, and the very next Step 8 run
now hard-fails on that pre-existing content, unrelated to whatever the
operator is currently touching. Two sibling gates in the same batch already
have a carve-out, but for reasons specific to their own subject matter — this
finding is that these two do not, and their subject matter offers no such
specific reason.

## What already exists here

- A near-identical class of problem (a different gate hard-blocking on
  content that predates the gate) was already solved once, for a different
  F11 verifier gate, with a one-time resolved-commit transition rule scoped
  to that gate's own rollout date.
- Two OTHER gates in this same batch already carry a scope-based carve-out
  for `scope == "extension"` projects, for reasons specific to their own
  subject matter.

## What would newly, permanently exist

A small module that resolves, per calling project, the commit at-or-before a
fixed historical instant (when these two gates first existed) and reads that
project's own `spec.md` text at that commit. The two gates' wiring would call
it — lazily, only when a candidate violation is found — to check whether the
violating content already existed, unchanged, at that historical point. This
becomes a permanent piece of the gate family's own logic: a fixed historical
reference point plus a per-project git-resolution routine that anyone
maintaining this gate family from now on needs to know about.

## Options on the table

- **A:** A one-time rollout/grandfather transition rule — content unchanged
  since before the gate existed is downgraded to advisory; anything new or
  edited since is judged normally.
- **B:** A permanent `scope == "extension"` skip for these two gates, mirroring
  the two sibling gates that already have one.
- **C:** Do nothing — leave both gates as unconditional hard blocks.

## Constraints that are not negotiable

none
