# ADR-112: A requirement states a phase's OUTPUT; the constitution states cross-cutting DISCIPLINE

- **Status:** accepted
- **Date:** 2026-07-26
- **Incident Reference:** iterate
  `iterate-2026-07-23-req3-phase2-content-mono` (REQ-3 Phase 2, the content
  round). Surfaced while walking `FR-01.05` (`/shipwright-build`), whose
  criteria had grown to twelve, most of them restating rules the constitution
  already binds every agent to.

## Context

The requirements catalog is meant to say **what the product guarantees**. The
constitution (`shared/constitution.md`) says **how every agent must work**,
everywhere, regardless of which phase is running: tests pass before a commit,
review happens in stages, commits follow a convention, a migration ships its
reverse, secrets never land in source, a destructive operation is confirmed
first, a changed UI is verified in a browser.

Those two had been quietly merging. Walking `FR-01.05` found seven of its twelve
criteria restating constitutional discipline — TDD, the review cascade,
conventional commits, tests-green-before-done. The same pattern was present, less
severely, in `.06`, `.07` and `.08`. Each restatement reads as a real guarantee,
so the catalog looked richer than it was while saying the same thing in four
places.

The cost is not aesthetic. Duplicated rules **drift**: the copy in one
requirement gets sharpened, the copy in another does not, and the reader has two
statements of one rule with no way to tell which is current. It also breaks
traceability — a test proving "tests pass before commit" would be bound to four
different requirements, none of which owns it.

## Decision

Three homes, and a rule for choosing between them:

| The statement is about… | Home |
|---|---|
| what one phase must **produce** for it to have succeeded | that phase's functional requirement |
| how an agent must **work**, in every phase | `shared/constitution.md` |
| **how well** something must perform, measurably | a quality requirement |

Concretely:

- A functional requirement states its phase's **output** and the properties of
  that output — what exists afterwards, what it refuses, what it deliberately
  will not do. It does **not** restate discipline that applies to every phase.
- Cross-cutting discipline lives in the constitution **once**, and reaches every
  client through the plugin: each skill's First-Actions reads
  `shared/constitution.md`. There is no per-client copy, so nothing drifts.
- Where a phase FR previously carried a constitutional rule, the rule was
  removed from the FR and — where the constitution did not already state it —
  added there instead. `FR-01.05` was trimmed from twelve criteria to **five
  phase-specific ones** in exactly this way (the removed seven were not lost —
  they were relocated or already present), and the walk then *added* three:
  the central outcome criterion and two build-specific guarantees. It carries
  **eight** today, not five; the trim and the additions are separate moves and
  an earlier draft of this record conflated them.

**A rule moved into the constitution still owes an enforcement declaration.**
Moving a sentence does not make it enforced, and the constitution's own
enforcement table names roughly four hooks against roughly forty rules — which
invites the reader to assume the rulebook is enforced when most of it is
instruction only. The register that makes the declaration mandatory is designed
(`.shipwright/planning/campaigns/2026-07-24-req3-constitution-enforcement-register-DESIGN.md`,
REQ-3 Phase 3) and not built. Until it lands, every rule not named in that table
is instruction-only, and the constitution now says so in its own text.

## Alternatives rejected

- **Leave the duplication.** Cheapest, and the status quo. Rejected because the
  drift is not hypothetical: the round found the review-cascade rule stated in
  three places with three different degrees of sharpness.
- **Delete the discipline from the constitution and keep it per phase.** Puts
  the rule next to where it applies, which reads well. Rejected because the
  discipline genuinely is cross-cutting: retiring one phase would silently
  retire rules that bind every other phase, and a new phase would start with
  none of them.
- **A fourth home — a "discipline requirements" section in the catalog.**
  Rejected as a rename of the constitution with worse reach: the catalog is not
  read by agents at work; the constitution is, by every skill's First Actions.

## Consequences

- Phase requirements get **shorter and more honest**: what is left is what that
  phase alone owes.
- One statement of each rule, in the place agents actually read.
- **Hard to reverse**, which is why this is recorded: the criteria removed from
  `FR-01.05` and its siblings are gone from those rows. Restoring the old shape
  means re-authoring them, and anyone doing so would first have to rediscover
  why they were removed — which is precisely the question this record answers.
- A boundary case remains and is deliberately unresolved: a rule that is
  cross-cutting **and** whose output is a phase artifact (the review record is
  the example) is stated in both, once as discipline and once as the artifact
  the phase must produce. That is not duplication — the two say different
  things — but it is the seam where duplication will try to creep back in.
