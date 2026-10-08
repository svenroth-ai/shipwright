# Architecture Brief: finalization gate registry + shared reason-code vocabulary

## The problem
Eleven follow-up units each need to add a finalization (F11) gate, and every gate must make the agent answer with a
code from a closed list instead of free text. The only check list lives in a file that is at its size cap and cannot
grow, and the review record stores "why did this not run" only as a free-text sentence.

## What already exists here
- `iterate_checks.run_all_checks` - the one hard-coded list of F11 checks (size-capped, ADR-125).
- `UNTESTABLE_REASON_CODES` - one closed list, defined inside that same file.
- Review record (`reviews.json`) with a free-text `disposition`; `record_review_pass.py` writes it.
- F5c iterate entry: free-form JSON, validated for a few fields only.

## What would newly, permanently exist
A small registry module that `run_all_checks` splices in once, one shared module holding the closed code lists per
check family, an optional `reason_code` field on review rows, and an optional `exemptions` block (count plus items) in the F5c entry
with one registered check validating it. The repository's tests keep the registry and its documentation table in step.

## Options on the table
- **A:** registry module + shared vocabulary module + optional fields, as above.
- **B:** extract the existing check list out of the capped file wholesale into a new module, then let units edit that.
- **C:** do nothing now; each later unit edits the capped file and raises its bloat exception.

## Constraints that are not negotiable
Old review records and F5c entries (65+ immutable histories) must stay readable; the capped files must not grow;
writers and validators ship together.
