# Architecture Brief: enforce the small-iterate code-review trigger

## The problem
A small change that touches a risky area or is larger than about 100 lines is supposed to get a code review. Today
nothing checks that it did, and the "100 lines" is counted differently in each of the three places that mention it,
so two tools can disagree about whether a review was due.

## What already exists here
- The F11 finalization verifier with a registry for new claim checks (`CLAIM_CHECKS`).
- A review record per run, where every review type is answered; at medium+ a floor requires a real code review.
- Step 3.4 of the campaign runner, which counts diff lines and decides whether reviews are required.
- A closed vocabulary of reason codes for a review that did not run.

## What would newly, permanently exist
One more F11 check (runs at small only) that re-measures the branch diff and re-reads the risk flags, then requires
the code-review row to be either completed or closed with a reason code. One shared module that defines the line
count once, used by both Step 3.4 and the check. The verifier's maintainers keep it correct.

## Options on the table
- **A:** a new registered F11 check plus one shared definition of the count.
- **B:** extend the existing medium+ code-review floor down to small.
- **C:** fix only the documentation so all three places describe the same count; no enforcement.
- **D:** do nothing.

## Constraints that are not negotiable
`iterate_checks.py` cannot grow (size cap); shared code cannot be imported into the plugin through the `lib` package
name (module collision, ADR-044/045).
