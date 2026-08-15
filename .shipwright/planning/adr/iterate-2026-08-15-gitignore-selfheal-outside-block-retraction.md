# Gitignore retraction reaches rules that predate the managed block

## Context

`shared/templates/shipwright-gitignore.template`'s SUPERSEDED block lets a
template revision retract a rule it previously shipped, stripping it from a
target project's `.gitignore` in the same pass that adds the replacement.
`_strip_superseded` (in `shared/scripts/lib/gitignore_canon.py`) originally
only stripped a match found *inside* the managed BEGIN/END block. Field data
(shipwright-webui, verified 2026-08-15) disproved the assumption that a
matching line outside the block is always a project's own hand-written rule:
webui's `/.shipwright/agent_docs/decision-drops/` blanket ignore was written
by `/shipwright-adopt` Step E on 2026-05-20, over two weeks before that
project's managed block was first scaffolded (2026-06-07) — so the retracted
rule sat outside the block purely because the marker convention did not yet
exist on that project when it was adopted, not because a human authored it.
The retraction (from iterate-2026-08-08-track-decision-drops) never actually
reached that live repo: the directory has silently stayed ignored for over a
week, losing every iterate ADR drop.

## Decision

Extend `_strip_superseded`'s scope to also cover the region *before* an
unambiguous single managed block (exactly one BEGIN, one END, in that order),
and to strip anywhere when no markers exist yet at all. A match found *after*
a well-formed block is still preserved — nothing this module ever writes
lands past a block's END marker, so content there is always a project's own
later addition. A malformed file (duplicate/unmatched/reversed markers) falls
back to a bounded scope: only the first complete BEGIN-to-following-END
region is eligible, computed explicitly rather than via a toggle that
re-arms on every BEGIN marker — the toggle form was shipped first and then
caught, by the external code-review cascade, silently re-widening scope into
a second complete marker pair (`BEGIN/END/BEGIN/<rule>/END`), which directly
violated the malformed-case "never widens" guarantee this same change
documents. All three marker-shape branches now compute a single `(lo, hi)`
line-index bound and share one filter loop.

Ownership-safety for the wider scope rests on every SUPERSEDED entry being a
curated `/.shipwright/`-namespaced literal path a project would not
plausibly author independently — documented in the template's SUPERSEDED
header as a standing constraint, and mechanically enforced by
`test_superseded_entries_stay_shipwright_namespaced` so a future entry that
drifts from that shape fails a test rather than silently inheriting the
same broad-strip reach.

## Consequences

An already-adopted project carrying a rule the template has since retracted
now self-heals on the next `/shipwright-adopt` or `/shipwright-project` run,
regardless of whether that rule sits inside, before, or (for a markerless
project) anywhere relative to the managed block — closing the gap the
original retraction left open. Out of scope: hand-fixing shipwright-webui's
own already-drifted `.gitignore` (separate card; the fix here only repairs
the mechanism for all future runs) and recovering ADRs already lost before
this fix lands.

## Rationale

Position-scoping (rather than reasoning about authorship) is the only signal
available to a pure text transform with no git-blame or timestamp context,
and it is sufficient once the SUPERSEDED entry shape is constrained to be
`/.shipwright/`-namespaced — a project's own content living at that exact
path, verbatim, immediately before its own managed block is not a
realistic collision this template has ever needed to protect against, versus
the real, observed failure of never retracting at all.

## Rejected alternatives

- **Reasoning about authorship/git-blame per line** — no such signal is
  available to a pure text-processing function operating on a `.gitignore`
  string; would require shelling out to git per merge call for no
  proportionate benefit.
- **Extracting `_strip_superseded` into a sibling module** — attempted, then
  reverted: a bare `from lib.X import Y` re-import inside
  `shared/scripts/lib/*.py` collides with `sys.modules['lib']` across
  plugins whenever a consumer (`write-project-config.py`) already imported a
  same-named `lib` package first, silently resolving against the wrong
  plugin's `lib`. Kept the module intra-`lib`-import-free instead.
- **Treating any malformed marker file as "strip nothing"** — considered for
  simplicity, but a malformed file with an unambiguous first complete pair
  still deserves the same protection a well-formed block gets; the bounded
  first-pair scope achieves both safety and utility.

## Test Completeness

`shared/tests/test_gitignore_canon_retraction.py` (12 cases) and
`shared/tests/test_gitignore_selfheal_retraction.py` (2 cases) cover all
three marker-shape branches, the before/after-block boundary, idempotency,
the malformed-duplicate-marker fallback, and the second-malformed-pair
regression the external code-review cascade caught. Full session narrative
(4 external plan-review rounds, code-reviewer, doubt-reviewer,
opus-plan-reviewer, and the external code-review finding) is in
`.shipwright/planning/iterate/2026-08-15-gitignore-selfheal-outside-block-retraction.md`.
