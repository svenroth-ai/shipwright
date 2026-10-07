# Architecture Brief: requirement-coverage commit gate

## The problem
The pre-commit coverage soft-block is meant to stop commits while too few requirements are verified, but on adopted projects it reads a number that does not exist and so never fires.

## What would newly, permanently exist
Nothing standing. This changes machinery that already exists: the compliance plugin's check_rtm_coverage hook now reads the committed traceability manifest (one small pure module) instead of an RTM line, and reports unmeasurable cases as warnings.

## Options on the table
- **A:** Read the committed manifest in the hook (FR and AC metrics), keep the old line as fallback.
- **B:** Make the RTM generator emit a requirement-coverage line and keep the hook reading the RTM.
- **C:** Do nothing / correct the documentation to say the hook measures build-section commits only.
