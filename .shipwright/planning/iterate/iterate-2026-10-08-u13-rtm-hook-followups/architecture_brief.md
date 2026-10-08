# Architecture Brief: honour a logged "Continue anyway" for the two compliance soft-blocks

## The problem
Two commit/deploy soft-block hooks tell the agent that the user may say "Continue anyway" and that the override must be logged. Neither hook reads that log, so after the user agrees the very next attempt is blocked again: the advertised escape hatch does not exist, and agents work around the gate instead. Separately, the coverage gate counts requirements whose tests simply were not run as uncovered, and it measures the current directory rather than the repo a `git -C <path> commit` targets.

## What already exists here
- `compliance_overrides.log` under `.shipwright/agent_docs/`, tracked in git, appended by hand or by `override_logger.log_override`; read by compliance reports as an audit trail.
- Both hooks soft-block with exit 2 and fail open on internal errors (`hook_failopen`).
- The coverage figure comes from the committed traceability manifest; a manifest with no executed result is already reported as unmeasurable.

## What would newly, permanently exist
A rule inside both hooks: an override-log entry naming the hook, with a reason, lets that hook through for 30 minutes after its timestamp, with a visible warning each time. The log becomes an input to the gates, not only an audit trail. One shared module holds the rule; the hooks' block message names the exact line to write. Kept correct by the compliance plugin's tests.

## Options on the table
- **A:** time window (30 minutes) after the entry, any number of passes.
- **B:** single use: the first command let through consumes the entry.
- **C:** keep the log as an audit trail only and tell the agent to ask the user to run the command manually.
- **D:** do nothing.

## Constraints that are not negotiable
The operator decided (2026-10-08): the override is logged and time-limited (30 minutes), applies to both hooks through one shared helper, and the block message names the line to write; a requirement whose tests did not run is "not measured", never covered or uncovered.
