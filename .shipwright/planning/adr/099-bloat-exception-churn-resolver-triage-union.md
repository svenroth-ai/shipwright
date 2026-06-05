# ADR-099: Bloat exception — `resolve_churn_conflicts.py` raised to 318-LOC

- **Status:** accepted
- **Date:** 2026-06-05
- **Re-Review-Date:** 2026-09-05 _(check whether the git-I/O reconcile helpers
  (`_reconcile_events`/`_reconcile_triage`/`_reconcile_logs`/`_union_conflict`)
  should move to a `churn_resolve_io.py` module, or the exception can be retired)_
- **Incident Reference:** sub-iterate C2 of campaign
  `2026-06-05-track-triage-jsonl` (`iterate-2026-06-05-triage-track-c2-churn`) +
  its **code-review BLOCKER fix** (Codex review, 2026-06-05): a hard
  `.shipwright/triage.jsonl` merge-conflict in a target project (which lacks the
  monorepo-only `merge=union` driver) was resolved with `--ours`, silently
  dropping the other side's backlog items.

## Context

`resolve_churn_conflicts.py` is the git-orchestration tool for churn-artifact
merge reconciliation. The **pure** allowlist/classify/dedup/validate logic was
already split out into `churn_merge.py` (which stays at 190 LOC) precisely to
keep this tool lean. C2 added triage to the reconcile path (`_reconcile_triage`
+ `_reconcile_logs` + `triage_invalid` status), trimmed to land at 298 LOC. The
Codex BLOCKER fix then added `_union_conflict` (union both conflict stages so a
hard triage conflict keeps BOTH sides) + the `triage_invalid` stderr branch,
pushing the tool to **318 LOC**.

## Ousterhout Argument

This is a **deep module**: a narrow interface (`complete_merge(project_root,
run_id) -> ResolveResult`) over substantial git-plumbing (conflict
classification, three-stage union, per-artifact `--ours`/`--theirs`/regenerate
strategies, two append-only-log reconcilers). The remaining bulk is *git I/O*
that cannot live in the pure-logic `churn_merge.py` (which is `no git / no IO`
by contract). Splitting the four `_reconcile_*`/`_union_conflict` helpers into a
separate IO module is plausible but would scatter one cohesive merge-resolution
flow across two files and add an import seam — deferred to the Re-Review-Date.

## YAGNI Check

Every added line is needed **today**: `_union_conflict` is the *only* cross-
project safety net against silent backlog loss on a hard triage conflict (the
`merge=union` driver is monorepo-only); the `triage_invalid` stderr branch makes
a real abort actionable. No speculative scope.

## Chesterton-Fence Check

The file is large because churn reconciliation has many cohesive cases (events,
triage, test_results, derived MDs, regeneration), each with a documented
strategy. git history shows it grew case-by-case under that structure; adding
the triage union case is consistent with the fence, not a violation.

## Decision

Add `shared/scripts/tools/resolve_churn_conflicts.py` to
`shipwright_bloat_baseline.json` at **318** (`state: exception`, `adr: ADR-099`).
`churn_merge.py` (190) and `integrate_main.py` (188) stay unbaselined under 300.
Retire when the reconcile-IO helpers are split into their own module
(tracked at the Re-Review-Date).
