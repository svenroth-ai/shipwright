# Architecture Brief: binding-completeness-rollout-transition

## The problem

A framework enforcement rule that started applying to a project on a given
day can immediately block work on data that already existed before that day
— data nobody wrote with the rule in mind. One population where this has
already happened is measured, not hypothetical: a project promoted several
requirements' test-layer bindings from an inferred to an author-declared
state on the same calendar day a new gate covering exactly that data went
live, and that gate gives those bindings no leniency at all today. The next
ordinary change to any of them will block on a gap the gate itself could
never have been consulted about when the binding was written.

## What already exists here

- Three sibling F11 gates already regenerate a requirement→test manifest
  from git history (base + head) to judge a change: one already carries a
  "this data predates the rule, don't hard-block it" leniency for one
  specific category of that data (an inferred/legacy-sourced binding).
- That leniency is keyed on a label attached to the data, not on when the
  data was written — so it does not cover a binding that was always
  author-declared (never legacy-inferred) but simply predates the rule.

## What would newly, permanently exist

A fixed point-in-time reference (tied to when the rule itself started
applying) that every future evaluation of this gate consults, plus a
per-project mechanism that resolves what a given piece of data looked like
at that reference point in THAT project's own history, and compares it to
what the data looks like today. This point-in-time reference and its
resolution logic become part of the gate's permanent behavior — future
maintainers of this gate family need to know it exists and why, the same way
they already need to know about the existing label-based leniency.

## Options on the table

- **A:** Compare today's declared binding against what the SAME project's
  own history shows the binding already was at the fixed reference point;
  grant leniency only when it already matches.
- **B:** Extend the existing label-based leniency to also cover
  author-declared bindings unconditionally (drop the requirement that the
  data be legacy-labeled).
- **C:** Do nothing; instead separately estimate, without changing the
  rule's logic, how often this situation is likely to occur across many
  projects.

## Constraints that are not negotiable

none
