# Iterate: atomic-frs cut 1 - delivery criteria move out of FR-01.11 into FR-01.22

Run: `iterate-2026-11-13-atomic-frs-cut-delivery` · Type: change · Complexity: small · Branch: `iterate/atomic-frs-cut-delivery`
Campaign: `.shipwright/planning/campaigns/2026-11-08-atomic-frs-BRIEF.md`. Follows the gate work in the U2b-prep PR (#1031). This is the first real cut; it needs the operator's approval before merge.

## The list of cuts
| Cut | Takes | Becomes | Done here |
|---|---|---|---|
| 1 | FR-01.11 AC21-AC25 | FR-01.22 "Delivering a finished change when the host cannot merge it" | yes |
| 2 | FR-01.11 AC30-AC34, AC37 | a later FR | NO - separate PR on the operator's word |

## What changed
- `.shipwright/planning/01-adopted/spec.md`: new FR-01.22 row and section; AC21-AC25 moved word for word; five `## AC-Move-Map` rows `FR-01.11/ACnn -> FR-01.22/ACnn`. Produced by `fr_split --apply` (conservation check ok).
- `shared/tests/test_deliver_pr*.py`: seven `covers(...)` tags re-pointed to FR-01.22 (by the tool).
- `shipwright_ac_registry.json`: FR-01.22 at 25; FR-01.11 raised from a stale 29 to 51, the highest AC the spec already uses (a correction, not a ratchet).
- `integration-tests/`: three tests pinned the catalog at 21 requirements; raised to 22, heading/anchor order compared sorted because `fr_split` places a new section right after its source.
- `shared/fr-authoring.md`: names that ripple for the next cut.

## Checks
- Keystone AC gate and orphan-AC-binding gate: clean on a probe commit with a freshly regenerated manifest (the committed manifest is a derived snapshot and lags until CI regenerates it).
- F0: full suite green, as a resumed run; `integration-tests` root 685 passed.
- Reviews (all opus): spec PASS, code PASS, doubt found the catalog-pinning tests (fixed). Plan, plan_internal, architecture_internal and external_code are below the small-complexity threshold.

## Spec impact
modify: FR-01.11 (five criteria leave), new FR-01.22.

## Known limits
- Old ids in historical records (decision log, campaign briefs) resolve through the move map.
- A parallel PR that mints FR-01.22 would collide; fetch and re-run the dry run right before the push.
