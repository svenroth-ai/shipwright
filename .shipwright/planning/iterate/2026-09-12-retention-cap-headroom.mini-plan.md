# Mini-Plan: Retention cap headroom

## Chosen approach

Raise `ITERATE_RETENTION` in `shared/scripts/tools/append_iterate_entry.py`
from `50` to `200`. Update its inline comment, the module docstring's
retention bullet, and `plugins/shipwright-iterate/skills/iterate/references/F5c.md`'s
retention section so all three keep saying the same number. Add a small
regression test asserting the new constant value and that the docs mirror it.
Record a new ADR entry amending (not reversing) the 2026-08-15 ADR's
steady-state assumption.

TDD order: write the failing constant/doc-consistency test first, then bump
the constant and the three prose locations, then re-run the full retention
test suite (`test_retention_merge_overshoot.py`, `test_retention_race.py`,
`test_append_iterate_entry.py`) to confirm nothing hardcodes `50`.

## Alternative considered and rejected

**Move retention to a main-only post-merge step or dedicated maintenance
command** (leverage-order item 2 from the investigation). Rejected for this
run: the 2026-08-15 ADR already evaluated adding merge-time/periodic
machinery for the same problem class and declined it, specifically because
this framework has no merge-time hook and a periodic sweep would be a new
scheduled surface. Nothing about today's evidence changes that cost/benefit
— it only shows the existing self-heal has less headroom than assumed, which
a cap bump directly addresses without new machinery. If the raised cap turns
out insufficient, this alternative is the next escalation and belongs in its
own iterate with its own review.

**Guard F6/pre-commit against staging a deletion of another run's entry
file** (leverage-order item 3). Rejected: this is retention's designed
behavior (evict the oldest *unpinned* entries, which by construction belong
to other runs), not a bug shape distinguishable from a fault at commit time.
A guard here would either always fire (defeating retention) or need the same
"is this deletion within the mechanism's own accepted overshoot bound"
judgment the self-heal test already encodes — i.e. it would duplicate
`test_retention_merge_overshoot.py` rather than add coverage.

## Files touched

- `shared/scripts/tools/append_iterate_entry.py`
- `plugins/shipwright-iterate/skills/iterate/references/F5c.md`
- `shared/tests/test_retention_cap_headroom.py` (new)
- `.shipwright/planning/adr/` (new decision drop via `write_decision_drop.py`)
