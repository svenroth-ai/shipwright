# Architecture Brief: make the end-to-end surface check impossible to talk past

## The problem
Before a medium-or-larger change is finished, someone has to actually drive what a person can see or use (a page, a
command, an interface) - or record "none" if there is nothing to drive. Today "none" is accepted with any sentence
of explanation, and the reported "N tests ran, all passed" is whatever the run typed in. Nothing compares either
claim with the change itself or with the test results that were actually saved.

## What already exists here
- The F0.5 runner (`surface_verification.py`) and the F11 finalization check that reads its block.
- A closed vocabulary of reason codes shared by all finalization checks.
- Staged test evidence: each run's real runner reports with a provenance file naming the run and the commit, already
  read by the cross-layer coverage gate.
- A merge-base diff measurement and a frontend-file detector used elsewhere.

## What would newly, permanently exist
A list of path rules saying which changed files are a runnable surface (UI, API route, SSE/WebSocket, message
contract), one more reason-code family, and a comparison of the block's numbers with the staged evidence. The
verifier's maintainers keep the rules accurate.

## Options on the table
- **A:** re-derive "is there a surface" from the diff, require a closed code for "none", and compare the numbers with
  the staged evidence (provenance + parsed reports).
- **B:** only require a closed code for "none"; keep trusting the numbers.
- **C:** have the F0.5 runner record its own revision and re-check only that file, not the staged evidence.
- **D:** do nothing.

## Constraints that are not negotiable
`iterate_checks.py` and `surface_verification.py` cannot grow (size caps); shared verifiers must not import the
compliance plugin eagerly (ADR-044/045).
