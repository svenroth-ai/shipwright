# ADR-120: The coverage gates ask the diff, not the recorded complexity

- **Status:** accepted
- **Date:** 2026-08-01
- **Incident Reference:** `iterate-2026-08-01-coverage-gate-recompute-order`
  (supersedes `trg-f872a6d7`; re-homed off the IT-3 anchor, which had closed as
  PR #498 two days before the card was filed and so was carrying no owner)
- **Supersedes:** the MUST-FIX 1 carve-out ("an infra gap SKIPs below medium")
  and the reading of SHOULD-FIX 6 under which `check_removal_coverage` could
  document itself as running at all complexities while concluding at none of
  them.

## Context

Two F11 verifier gates stood down below `medium` complexity while their own
docstrings claimed they could not be dodged.

`check_integration_coverage` read the run's **recorded** complexity at
`integration_coverage.py:68-69` and returned a green `SKIPPED` at `:70-72` —
before reaching the diff recompute at `:76-80` that its docstring advertised as
the anti-dodge property. Non-dodgeability was a property of the *flag*
(recomputed, never self-reported); it was never a property of the *gate*, which
was keyed on a self-reported label sitting one field over.

`layer_coverage._infra_result` at `:99-106` turned a missing `--commit`, an
unresolvable base ref, a failed regeneration and a verifier exception into a
green SKIP whenever complexity was below medium — while
`check_removal_coverage`'s docstring said it "Runs at ALL complexities (a
removal is never trivial)". Both statements were true at once only because
*runs* and *can conclude anything* had been allowed to drift apart.

Both defects are pre-existing. They became urgent because PR #506 capped the
fall-through classification prior at `small`, putting materially more runs into
the band where both gates stand down.

### The band is exactly the one that matters

`risk_taxonomy.cross_component` carries `min_complexity: "medium"`, so a
*detected* cross-component change is already escalated and the gate fires
anyway. The below-medium band is reachable **only** when detection failed at
classification time — the flag is diff-driven and Stage 1 has no diff, so it is
message-only until the Stage-2 Quick Scout runs its detector step, which is
prose the agent must remember to execute. The old order therefore made the
mechanical backstop depend on the outcome of the non-mechanical step it exists
to backstop.

## Decision

Move each complexity gate **below** the recompute so the diff decides, and make
infra failures fail closed at **every** complexity.

- The recorded complexity becomes message content (`_floor_note`), never control
  flow.
- Only a genuine **non-git context** still stands either gate down — that is an
  inapplicable context, not a failure.
- `check_removal_coverage` establishes the git context **before** checking for a
  commit. Load-bearing: in the original order the missing-commit branch fired
  first, so making it unconditional would have hard-failed every non-git project
  on a commit it was never going to have — a false-red manufactured by the fix.
- `check_cross_layer_coverage` keeps its medium+ scope. That is a deliberate cost
  decision about regenerating base/head manifests with execution evidence, not
  the verified loophole, and the card verified neither.

## Rationale

The repository already held the opposite decision for the sibling gate.
`ci_supplychain.py:168-170` documented *"Applies at EVERY complexity on purpose
(unlike the `cross_component` gate's medium+ floor): a one-line workflow edit is
still a trust-boundary change, and a complexity floor would be the obvious way to
dodge it"* — naming **this** gate's floor as the contrast.

So this is not a new posture. It is the resolution of a contradiction the
codebase was carrying, in favour of the later and better-evidenced side. The
supersession is recorded rather than the older text quietly edited.

`min_complexity: medium` on the `cross_component` flag is **retained**, and
re-stated across the runtime prose as what it always was: a *classification*
escalation floor, independent of whether the gate enforces. Coupling those two
readings is what produced the defect.

## Rejected alternatives

**Recompute first, but WARN below medium instead of failing.** Rejected on merit
and by the operator at the approval gate: a green SKIP and an ignored WARN are
indistinguishable to whoever ships the change, so this would relabel the loophole
rather than close it. It would also split the gate into two enforcement postures
keyed on the very field the fix removes from the decision.

**Extending the reorder to `check_cross_layer_coverage`.** Would make every
trivial run regenerate base/head manifests and demand executed-passing tests at
every required layer — a large cost for a gate the card did not verify.

**Migrating `check_ci_supplychain_ack`'s binary git probe** to the new tri-state
helper, and **teaching `lib/iterate_entry.py` to catch `UnicodeDecodeError`**.
Both are real and both are the same defect class, but each changes a surface
outside this card. Deferred with owners: `trg-20cc9ec8` and `trg-06216b9f`.

## Consequences

Runs that pass today can now fail:

- a below-medium iterate touching cross-component machinery with no
  `category:"integration"` behavior;
- a below-medium iterate whose removal-coverage regeneration cannot run.

Both are the intended effect. **Clearing the integration gate does not require
escalating** — recording the behavior in the run's own F5c entry works at every
tier, including `trivial`, where the Test Completeness Ledger is otherwise auto-
`n/a`. An earlier draft of the failure text claimed escalation was the only
route; that was false at source and would have sent trivial runs to buy a spec,
mini-plan, approval gate and external review they did not need.

Two hardening changes ride along, because the reorder widened their blast radius
from one gate at medium+ to two gates at four tiers:

1. **Ledger attribution.** The shared-`shipwright_test_results.json` fallback was
   read raw, with no run-id check, while three siblings guard the same file with
   `read_iterate_latest(...).is_current`. On a branch behind main F11 restores
   that file to HEAD, so an unattributed read sees the *previous* run's block — a
   cross-component change could pass green on someone else's integration test.
   Now attributed.
2. **Locale-independent git classification.** `git_context` (promoted from
   `layer_coverage._git_context` to `git_helpers` so both gates share it)
   classified `not_git` by English substring alone. git ships gettext
   translations, so on a localized install a genuine non-git directory would have
   classified `git_error` — inverting the documented SKIP into a hard block on
   every non-git project. A structural fallback (`--show-toplevel`, then a `.git`
   search up the tree) now answers language-neutrally, while an empty stderr
   still means git never ran and stays `git_error`.
