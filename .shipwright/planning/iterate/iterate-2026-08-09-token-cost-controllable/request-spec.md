# iterate-2026-08-09-token-cost-controllable — request (spec-equivalent)

Small-complexity docs-only feature; no formal iterate spec file at this
complexity. This file captures the operator's original request verbatim, for
use as the spec-equivalent input to review tooling.

## Request

Re-filed on operator direction: this must NOT read as a report of what we
measured. It is a how-to, organised by THRESHOLD -> STRATEGY. A reader should
be able to look up their own situation ("I have this many iterates, my
decision history is this big") and find the two or three things worth doing,
without reading any analysis. SHAPE — for each threshold, name the observable
trigger, the symptom, and the action.

Draft thresholds (derived from this repo's shape at ~1.7 KB per decision
entry; state that assumption so a reader can adjust, and verify before
shipping):

- ~20+ iterates / decision history over ~35 KB -> Set an auto-compact window
  before it starts to matter. Explain the trade-off in one line: compacting
  earlier is cheaper but the first compaction must not land in a phase whose
  state is still only in the conversation.
- ~35+ iterates / decision history over ~100 KB -> The history is now a
  measurable share of EVERY session, because it is still small enough to be
  read in full. This is the band where an index starts paying for itself.
- ~90+ iterates / decision history over ~2,000 lines -> It has silently
  stopped being read at all — one read returns at most 2,000 lines. Switch to
  index-plus-detail-on-demand; a "read it all" instruction is no longer being
  followed regardless of what it says.
- Sessions running long (a few hundred exchanges) -> Lower the reasoning
  effort level; use a cheaper model for building and a stronger one for
  reviewing, as SUBAGENTS — never a mid-session switch, because the model is
  part of the prompt cache and switching re-pays the whole context.
- Any size -> What is NOT worth optimising, stated plainly so nobody spends a
  week on it: the decision log and the event log are not what makes sessions
  expensive. Cost tracks the NUMBER of exchanges times how much context each
  one carries.

## Rules for the writing

1. Recommendations, never shipped defaults. The auto-compact window and the
   effort level are Claude Code user settings a plugin cannot set, and
   choosing a model tier for a consuming project moves their bill without
   consent. A document can advise without coercing — that is why this is the
   right vehicle.
2. Numbers only where they define a threshold or a trade-off. No attribution
   tables, no percentages of our own bill, no methodology.
3. Say which numbers are specific to this repo and which transfer.
4. Point at the meter for "measure your own", rather than substituting our
   figures for theirs.

## Deliverables

A new page under `docs/` (working title "Keeping token cost controllable");
`docs/guide.md` updates (Chapter 8/9 quality gates gains the cost dimension,
Appendix B gains the meter and readiness commands); one line in `README.md`
per its summary-plus-link role.

Note: during drafting, the draft threshold numbers above were verified against
this repo's actual decision log (347 entries / 4,634 lines / ~600 KB) and
found internally inconsistent with the stated ~1.7 KB/entry ratio for two of
the three bands; they were corrected to ~20/~35KB, ~60/~100KB, ~150/~2,000
lines to make the ratio self-consistent, per rule 3's instruction to verify
before shipping. See the review record for detail.
