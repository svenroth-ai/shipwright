# Architecture Brief: adopt-miner-hygiene-gate-conflict

## The problem

`/shipwright-adopt` mines a target repo's own test-file labels (`describe`/
`it`/`test_*`) into `spec.md` acceptance-criteria bullets when no richer
enrichment source exists. Those mined bullets routinely carry code symbols
(component names) or HTTP verb+path text. A separate, existing hard-block
check on `/shipwright-project`'s own completion step rejects any acceptance
criterion carrying that kind of implementation detail, with no exemption
available for content produced after a fixed date. So an onboarded project
can end up with acceptance criteria that were legally written by the
project's own tooling, yet the tooling that checks them later refuses to
accept — and the person hitting the block did not write the offending text
and may not even know where it came from.

## What already exists here

- A pure detector function that names *what kind* of implementation detail a
  piece of text carries (code symbol, file path, HTTP verb, etc.) — already
  the single source of truth both the miner and the checking gate would need
  to agree on.
- A time-bounded "grandfather" mechanism for a *different* instance of this
  same family of conflict: content that already existed in a project's git
  history before a gate was introduced gets graded down to advisory. It only
  helps content with a *pre-gate* history; it structurally cannot help
  content a tool keeps generating after the gate already exists.

## What would newly, permanently exist

Nothing, under the option this run is leaning toward: the mining step would
simply stop producing text the detector already knows how to flag, using the
detector it already has. No new stored state, no new check, no new schedule.

Under the alternative gate-side option, a new standing exemption would exist:
some way for the checking gate to recognize "this content came from the
mining tool" and treat it differently forever, for every future onboarding —
a new thing to keep correct as the miner or the gate change independently.

## Options on the table

- **A:** Change the mining step so it does not produce text the existing
  detector would flag.
- **B:** Change the checking gate so it recognizes and exempts
  miner-produced content.
- **C:** Do nothing further — leave the conflict latent until a project
  happens to hit it, and handle each occurrence by hand at that point.

## Constraints that are not negotiable

none
