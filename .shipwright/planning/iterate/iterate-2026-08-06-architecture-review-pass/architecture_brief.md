# Architecture Brief: architecture-review-pass

> **This is the round-1 input, kept as evidence — NOT a model brief.** It
> describes the design the reviewers were asked about and then REJECTED: a
> per-run `Standing mechanism:` declaration, a conditional trigger and a new
> review-record row, none of which shipped. Its header field and its "what would
> newly exist" section therefore contradict both the delivered scope and
> `shared/templates/architecture_brief.md`, which is the template to copy.

- **Run ID:** iterate-2026-08-06-architecture-review-pass
- **Standing mechanism:** other:review-pass

## The problem

Every review this project runs judges a change *within* the frame its plan set.
Three reviewers check the code diff against the spec (does it fulfil the
acceptance criteria, is it correct, do its claims hold); a fourth reviews the
implementation plan against the specification. On one measured change — roughly
5000 lines of delivery machinery — three review rounds produced 25+ findings and
not one of them asked whether the mechanism should have been built. The same
change, put to the same two external models over a short problem statement
instead of the plan, was rejected by both, each independently naming a simpler
alternative. A second, independent change reproduced it. The cost of the miss is
paid forever: mechanisms that should not exist get maintained, reasoned about
and worked around by every subsequent change.

## What already exists here

- Four review passes over a diff: `spec-reviewer` (acceptance criteria),
  `code-reviewer` (correctness), `doubt-reviewer` (adversarial), and an external
  two-model code review. All run after the code is written.
- One external two-model review of the implementation plan, before building.
  Its input is the plan document, which contains the author's chosen approach
  together with its justification.
- A self-review checklist whose first item is "architectural soundness",
  answered by the author over their own plan.
- A per-run review record: one row per review type, each closed with a result
  or an explicit reason it did not run. A finalization gate stops any run that
  leaves a row unanswered.
- Two gates that recompute a risk condition from the actual change set and stop
  the run if the required evidence is missing. Both work off an exact list of
  file paths.

## What would newly, permanently exist

A fifth review pass, run before building, asking one question: should the new
permanent mechanism this change introduces exist at all, and what is the
smallest thing that would do. It is a second call to the same two external
models inside the existing review step, and it reads a separate short document
written for it rather than the plan.

It comes with a per-run declaration (`Standing mechanism: none | workflow |
credential | scheduled_job | write_surface | other:<x>`) that decides whether it
runs, a document template, a prompt, and a row in the review record that the
existing finalization gate refuses to leave unanswered.

Kept correct from now on by: whoever edits the review step, the prompt, or the
declaration vocabulary. Nothing detects when the declaration is wrong.

## Options on the table

- **A:** Add the architecture question as an extra instruction to the existing
  plan-review prompt. No second call, no new document, no declaration, no new
  row; it runs on every plan review.
- **B:** A second call to the same two models inside the same review step,
  reading a separate short document that omits the author's reasons for
  rejecting the alternatives. Runs only when a per-run declaration names a new
  permanent mechanism. Enforced by a row in the existing review record.
- **C:** As B, plus a check at the end of the run that re-derives from the
  actual change set whether a new permanent mechanism appeared, and stops the
  run if the pass was skipped.
- **D:** Do nothing. Keep four review passes and accept that no pass asks the
  question.
- **E:** Make the existing plan review read a problem statement instead of the
  plan, changing its question rather than adding a pass.

## Constraints that are not negotiable

- The review record is a cross-repository contract with a separate consumer.
  Roughly 120 records already on disk are git-tracked and immutable; nothing may
  make them read as corrupt.
- The finalization gate that reads that record fails closed.
- Whatever runs must go through the existing two-reviewer path, so that a
  disagreement between the two models stays visible instead of being averaged
  into a finding count.
