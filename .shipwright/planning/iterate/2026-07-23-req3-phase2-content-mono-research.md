# Gap check: our coverage checklist vs. established requirements practice

Run: `iterate-2026-07-23-req3-phase2-content-mono` (REQ-3 Phase 2).
Reason: before writing 15 more requirements, check we are not about to
rediscover common sense one requirement at a time. Prompted by the operator
after finding 4 (criteria described workflow, not outcome) — a textbook fault we
found by accident.

**The filter applied to every candidate**, per operator instruction (*"pragmatisch,
nicht by the book … so umfassend wie nötig, aber nicht umfassender"*):

> Would omitting this let a real defect through **for a solo developer or a
> three-person team**? → adopt.
> Is it there so a document looks complete to an assessor? → reject, and say why.

We are not building for audit. If the market later demands it, that is a
different exercise.

## Result in one line

**No dimension is missing.** Our seven — Outcome · Purpose · Boundaries & edge
cases · Failure behaviour · Glossary terms · Rationale · Out of scope — cover
the ground. Three **sharpenings** and one cross-reference; **zero new
dimensions.**

## Adopt

| # | From | What | Why it survives the filter |
|---|---|---|---|
| A1 | Volere test 4 — *term consistency* | Once a term is defined, it is used that way everywhere. Goes into §4, which already says to sharpen terms but not to keep using them consistently. | **We created this exact defect today**: `split` / `section` / `buildable piece` — three words, two concepts, one of them invented mid-session by me. Costs nothing to check, and catches the thing that makes two readers understand a requirement two ways. |
| A2 | Volere *fit criterion* + ISO 29148 *verifiable* | Sharpen **Outcome** from "what must exist afterwards" to "…and how would you tell it is any good — a question you can answer yes or no". | Our Outcome dimension asks what exists, not how you would know it is right. Volere's framing is the sharper one and it is the same idea we arrived at the hard way: *"an objective measure of the requirement's meaning"*. Without it, "a requirements catalogue exists" passes while the catalogue is empty. |
| A3 | ISO *necessary* + Volere test 9 — *stakeholder value* | Add to the Purpose question bank: **"what happens if we don't build this?"** | Pure scope discipline, and the cheapest question in the set. For a small team the binding constraint is what to cut, not what to add. One question, no new dimension. |

## Cross-reference, not adopt

| From | Status |
|---|---|
| Volere test 8 — *no solution disguise* (state the business need, not the technology) | **Already ours** — `fr-authoring.md` §1 "keep the guarantee, drop the mechanism" and §2 altitude. Not duplicated into the checklist; the checklist links to it so the two cannot drift. |
| Volere test 10 — *unique identification* | Already ours — permanent FR IDs, never renumbered (`fr-authoring.md` §4). |
| ISO *singular* | Already ours — "one behaviour per line" in the catalogue preamble. |

## Reject, with reasons

| From | Rejected because |
|---|---|
| ISO *feasible* | Whether it can actually be built is settled by planning, which researches and reviews. Asking it at elicitation front-loads speculation from the person least able to answer it, and a wrong "yes" here is not caught by anything. |
| Volere test 7 — *stakeholder exploration* (conscious / unconscious / undreamed-of needs) | The useful half is already in Purpose ("who is 'someone'?") and in §8.1's negative-space pass. The rest is an enterprise practice: a solo developer building their own tool has one stakeholder, and the ceremony would be pure theatre. |
| Volere tests 2 & 5 — *relevance to a context diagram*, *adequate context* | Requires a context diagram we do not produce and would not read. No defect prevented for a three-person team. |
| ISO *correct*, *conforming*, *appropriate* | Assessor vocabulary. They describe conformance to a process, not properties whose absence lets a defect through. This is exactly the "holds up to an audit" work we are deliberately not doing. |
| ISO *complete*, *unambiguous* (as separate checks) | Not separable in practice from the plain-language rule plus a fit criterion. Adding them as their own rows would make the checklist look more rigorous while changing nothing anyone does. |

## What this says about the five findings from the walk

Findings 3 and 4 are textbook — *"describing process instead of outcomes"* is
named as a top acceptance-criteria mistake in the practitioner literature, and
the fit criterion is the same idea with fifty years on it. We would have got
there faster by looking. Findings 1, 2 and 5 are **ours** and have no equivalent
in the sources: the prompt-versus-code verdict and the "assumed only when
unobtainable" rule are specific to agent-written requirements, which the
standards predate.

## Sources

- ISO/IEC/IEEE 29148 — <https://www.iso.org/standard/45171.html>, <https://www.reqview.com/doc/iso-iec-ieee-29148-templates/>
- Volere, *Ten Tests for Requirements* — <https://www.volere.org/ten-tests-for-requirements/>
- Volere requirements shell / fit criterion — <https://www.volere.org/templates/volere-requirements-specification-template/>
- Acceptance-criteria practice — <https://www.altexsoft.com/blog/acceptance-criteria-purposes-formats-and-best-practices/>, <https://kollabe.com/posts/how-to-write-acceptance-criteria>
