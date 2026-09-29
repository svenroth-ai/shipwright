# Architecture Brief: campaign-runner-architecture-review

## The problem

The review that asks "should this be built at all?" runs for a normal iterate
but not for changes built inside an unattended multi-change campaign, although
campaign changes are exactly where new standing mechanisms tend to get built. The
campaign's per-change agent carries its own copy of the review step, sits exactly
at its size limit, and cannot ask a person a question when a reviewer says
"reject".

## What already exists here

- The normal iterate makes the second (architecture) call and stops to ask the operator on a reject.
- The campaign agent's own copy of the plan-review step (Branch A/B/C), which already records "missing keys" without blocking and reports it at campaign end.
- A result-file contract the orchestrator reads; an `escalated` status already stops the whole wave.
- A per-file size ceiling recorded in a baseline, with an ADR-gated exception mechanism.

## What would newly, permanently exist

A second reviewer call in the campaign agent, a new `escalated` reason code with
the verdicts carried inside the result file, and an orchestrator paragraph that
prints halted changes at campaign end. The result-file schema keeps them
consistent.

## Options on the table

- **A:** Move the campaign agent's copy of the review step into a shared reference file; add the second call there; on a reject, stop that change and hand the verdicts to the orchestrator to show at campaign end.
- **B:** Keep the copy inline, raise the size ceiling with a new exception, add the second call there.
- **C:** Make the campaign agent point at the normal iterate's step instead of any copy, and describe only the differences.
- **D:** Do nothing; keep the documented gap.

## Constraints that are not negotiable

The campaign agent cannot ask a person anything while running. No new size
exception may be minted for this change.
