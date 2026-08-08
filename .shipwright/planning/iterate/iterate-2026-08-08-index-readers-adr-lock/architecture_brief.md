# Architecture Brief: index-readers-adr-lock

## The problem

Two independent problems on one "instruction promises more than the system
delivers" surface. (1) Four skill files across four plugins instruct an agent
to read a 4,379-line file "completely," but a single read call caps at 2,000
lines — the guarantee is already silently broken on every run that loads it,
today, not in the future. (2) A folder of per-decision spec files is named
`<NNN>-slug.md`; the `<NNN>` is picked by unaided agent judgment when a
change branches, with no coordination between branches sharing a base. Ten
parallel changes branching the same night picked overlapping numbers: 6
numbers are currently claimed by 15 files combined, and the count has grown
by one pair since it was first measured a few hours ago.

## What already exists here

- A 331-line index (`decision_log_index.md`) of the 4,379-line file already
  exists and is already kept fresh by two writers — nothing currently reads
  it.
- The adjacent problem (numbering the OTHER decision log, `decision_log.md`
  itself) was already solved: writes go through a per-run "drop" file with no
  number, and a single serialized release step assigns the real number later
  — so two branches can never collide on that file's own numbering.
- A per-branch lock + index-render mechanism already exists for a sibling
  folder-index file in the same directory tree (unrelated to numbering
  collisions — it serializes writes to a rendered listing, not number
  claims).

## What would newly, permanently exist

For problem (2): an exclusive number-claiming mechanism — a lock file plus a
small persisted counter — that every future change consults before naming a
new per-decision spec file, scoped to one machine's linked working copies of
this repository. Something must keep that counter correct indefinitely (a
missing or corrupted counter is a live risk, not a cosmetic one), and every
future contributor writing this kind of spec file must now go through it
rather than picking a number by hand. Problem (1) adds nothing new — it only
changes which existing file four instructions point an agent at.

## Options on the table

- **A:** Claim the number exclusively at branch time, before the file is
  named — a lock + a durable, self-healing counter scoped to one machine.
- **B:** Leave numbering unresolved at branch time (as today) but resolve it
  centrally later, at the same single serialized point that already assigns
  the OTHER file's numbers, renaming the branch's provisional file to match.
- **C:** Claim the number via a network call (e.g. a git-ref push) that is
  atomic across machines, not just one.
- **D:** Do nothing to the allocation path; rely only on a test that detects
  a collision after the fact, once both branches have already merged.

## Constraints that are not negotiable

none
