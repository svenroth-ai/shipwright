# Mini-Plan: decision-log-drops-index

- **Run ID:** iterate-2026-08-07-decision-log-drops-index

## Approach

Mirror `shared/scripts/lib/adr_index.py`'s established split (pure
`render_*` + writing `rebuild_*`, lock + `durable_atomic_write`) into two new
modules, wiring each into the exact call sites that mutate its source:

1. `lib/decision_log_index.py` — parses `decision_log.md`'s own
   `### ADR-NNN: Title` headings (fence-aware), renders a sibling
   `decision_log_index.md`. Wired into `write_decision_log.append_decision`
   (direct path) and `aggregate_decisions._refresh_index` (release fold).
   Registered in `churn_merge.CHURN_ALLOWLIST`; refreshed post-merge by
   `integrate_regenerate.regenerate_after_merge`.
2. `lib/decision_drops_index.py` — same split for the gitignored
   decision-drops staging directory. Wired into `write_decision_drop.py`'s
   CLI and `aggregate_decisions._refresh_index`. NOT added to
   `CHURN_ALLOWLIST` and NOT given a CI drift guard against a committed
   copy — the directory is gitignored, so git can never conflict on it.

## Alternative approach — rejected

**Single shared "index framework" module** parameterizing render/rebuild for
all three artifacts (ADR folder, decision-log, decision-drops) behind one
generic interface. Rejected: the three sources have genuinely different
shapes (a folder of files vs. one Markdown file's headings vs. a folder of
JSON records), so a generic abstraction would need per-artifact hooks for
parsing, slugging, and churn-eligibility anyway — collapsing to roughly the
same code behind an extra indirection layer, for three call sites total.
Three small, independently-testable modules mirroring the ADR precedent are
simpler to review and to extend a fourth time later.

## Risk / LOC constraint

`write_decision_log.py` (377/377, frozen bloat-baseline ceiling) and
`aggregate_decisions.py` (270/303, real headroom) both needed edits. The
former required deleting a confirmed-dead `status` kwarg/CLI flag to make
room for the new refresh call without ratcheting the baseline.
