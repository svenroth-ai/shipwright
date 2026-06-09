# Sub-Iterate: S3 — Finalize wiring + churn resolver (regenerate-on-conflict)

## Scope

Worktree finalize: after work_completed is recorded, call regenerate_campaign_status -> write the worktree's campaigns/<slug>/status.json -> F6 stages it (ships in the PR). Demote campaign-mode 3g main-tree update-status to local-board convenience. Resolver: churn_merge.classify() treats .shipwright/planning/iterate/campaigns/*/status.json as resolvable via a glob predicate; add a regenerate branch in resolve_churn_conflicts mirroring DERIVED_MDS; wire into integrate_main.

## Acceptance Criteria

- [ ] F6 status.json round-trip (per-tree, PR-committed)
- [ ] classify-glob matches campaigns/*/status.json
- [ ] integrate_main concurrent-sibling regenerate; events_invalid still aborts
