# S2b pass C — explicit finding, include_iterate convergence, posix separators

**Run-ID:** iterate-2026-08-27-s2b-discovery-c
**Full detail:** `.shipwright/planning/iterate/2026-08-27-s2b-discovery-c.md`
**Campaign brief:** `.shipwright/planning/campaigns/2026-08-24-s2b-discovery-convergence-BRIEF.md`

## Context

Campaign S2b converges `planning_discovery`'s 15 call sites one flag at a
time. Pass C closes the last three open questions: how a broken (file, not
directory) planning path should surface at finding-capable sites, whether
`include_iterate` should default to excluding iterate/ run docs, and whether
`setup-design-session.find_specs` should emit OS-native or POSIX separators.

## Decision

Only `rtm.collect_external_review_states` converts its raise to an explicit
`ExternalReviewState(status="error", reason=...)` finding — its sibling
`collect_requirements` keeps raising, since its return type has no
status/reason slot and widening it was judged out of proportion to the risk
being closed. `include_iterate=False` flips at 9 of 12 remaining sites,
excepting `spec_parser._iter_spec_files` (R0 M6) and `setup_adopt` (a
disclosure list). `setup-design-session.find_specs` now emits
`.as_posix()`, and the OS-conditional `platform_sep` test apparatus is
removed as dead code. Two same-class defects outside the 15-site inventory
(`_test_links_io.discover_specs`, `backfill_test_links.discover_specs`
gating on `.exists()` instead of `.is_file()`) are fixed alongside, plus
five pass-B nits (renames, a liveness guard, comment/docstring placement,
two narrowed over-broad claims).

## Consequences

Four real nested `iterate/<run-id>/spec.md` files in this repo stop being
offered as adoption evidence, an FR source, or a design-session candidate at
the four recursive call sites — a genuine correctness fix, not merely
preventive. A stray file at `.shipwright/planning` now surfaces as one
finding row instead of crashing two compliance collectors. `find_specs`'s
sibling-directory sort order is now platform-invariant.

## Rationale

The operator-narrowed C1 scope (only the site whose data model already
carries a status/reason field converts) avoids introducing an unaudited
regression into `RequirementInfo`'s multiple downstream traceability
consumers for a case that was already broken. The C2 exceptions preserve two
already-decided, deliberately-different behaviors (R0's iterate/*.md special
case; setup_adopt's disclosure list) rather than steamrolling them under one
default.

## Rejected alternatives

Converting `rtm.collect_requirements` (#7) alongside #8 this pass — rejected
per the operator's explicit risk-first instruction: convert both only if
doing so introduces no regression risk, and #7's contract-widening could not
be ruled safe without auditing every consumer.

## Mid-flight corrections

See the iterate spec's own "Mid-flight corrections" and
"External-Code-Review-Findings" sections for a rebase-onto-moved-`origin/main`
correction, a diff-generation fix, two external-LLM-review fixes, and a
bloat-anti-ratchet fix — all resolved before commit, all re-verified green.
