# ADR-XXX: Bloat exception — `<path/to/file>` raised to <new>-LOC

<!-- Template for granting a bloat-baseline exception. Copy to
     `.shipwright/planning/adr/<NNN>-<slug>.md`, fill every field, and
     reference the new ADR-ID in `shipwright_bloat_baseline.json` (set
     the entry's `state` to `"exception"` and `adr` to `"ADR-NNN"`). -->

- **Status:** proposed | accepted | superseded
- **Date:** YYYY-MM-DD
- **Re-Review-Date:** YYYY-MM-DD _(mandatory — set 3 months out by
  default; the reviewer at that date checks whether the exception is
  still load-bearing or the file can finally be split)_
- **Incident Reference:** _(mandatory — link to the iterate / PR / issue
  / triage item where the limit was first crossed. Pattern only — do
  NOT verbatim-quote third-party text here; this is shipwright's own
  log. Inspired by the Multica `CLAUDE.md` per-decision incident-ref
  pattern (Multica is Apache-2.0 modified-with-hosting-restriction;
  patterns are reusable, text is not.))_

## Context

_(What is the file? Why is it bloated? What concretely changed in the
incident that pushed it past the limit?)_

## Ousterhout Argument

_(Mandatory. John Ousterhout's "Modules should be deep" — i.e. small
interface, substantial behaviour behind it. Argue that this file is a
**deep module**: the interface is genuinely narrow, the implementation
is genuinely substantial, and splitting would expose internals that
should stay encapsulated. If you cannot make this argument honestly,
do not file the ADR — split the file instead.)_

## YAGNI Check

<!-- Mandatory. Header adapted from obra/superpowers `writing-plans`
     skill (MIT, © Jesse Vincent). The check forces "is this size load
     of code actually needed right now, or are we carrying speculative
     scope?" -->

_(Mandatory. Walk through the file's responsibilities and ask, for
each one: "Do we need this **today**? Not "might we need it next
quarter" — today. If a responsibility fails the test, remove it
**before** writing the exception. The exception is for code that
genuinely cannot be deleted, not for code that could be deleted with
some work.)_

## Chesterton-Fence Check

<!-- Mandatory. Header adapted from addyosmani/agent-skills
     `code-simplification` (MIT, © Addy Osmani). The check forces
     "is the existing structure here for a reason I haven't seen?" -->

_(Mandatory. Before declaring "this file is too big and must be
exception-allowed", first ask: did some earlier review establish a
reason for the current shape? Read the git history of this file and
of any adjacent design docs. If the fence stands for a reason —
record the reason here, and the exception holds. If the fence stands
for no documented reason — tear it down (refactor) instead of granting
the exception.)_

## Decision

_(What is the new `current` value being granted? What is the
deliberate plan to retire the exception — refactor schedule,
dependency, blocking work?)_

## Consequences

_(Who else now operates against the new limit? Which tests or
downstream consumers need to update? What is the cost if the
exception holds longer than Re-Review-Date?)_

## Rejected alternatives

_(At least one: "just leave it at the old limit and split now"; "do a
shallow refactor"; "rewrite in a different language"; "delete the
feature". Argue each one down explicitly. Pure pro-forma alternatives
are a red flag — the reviewer should see real trade-offs here.)_

---

## External Sources Acknowledged

This template's YAGNI Check + Chesterton-Fence Check headings are
adapted from:

- obra/superpowers, skill `writing-plans` —
  https://github.com/obra/superpowers — MIT © Jesse Vincent
- addyosmani/agent-skills, skill `code-simplification` —
  https://github.com/addyosmani/agent-skills — MIT © Addy Osmani

The Incident-Reference field follows the **pattern** of the per-decision
incident-reference convention in `multica-ai/multica` `CLAUDE.md`
(Apache-2.0 modified-with-hosting-restriction — patterns reusable, text
not copied).
