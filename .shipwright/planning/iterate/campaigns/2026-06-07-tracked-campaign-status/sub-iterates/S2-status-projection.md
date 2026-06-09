# Sub-Iterate: S2 — Projection + regenerate producer (regenerate_campaign_status)

## Scope

New pure regenerate_campaign_status(campaign_dir, events_log): read campaign.md skeleton (ids/slugs/order/titles) + project events (extras.campaign==slug && extras.sub_iterate_id==id -> latest work_completed -> complete, carry commit/tests). Never-downgrade guard: status = max(committed, projected) over pending<in_progress<complete (failed/escalated explicit). Lifecycle recompute via the existing _all_subs_complete. Thin CLI wrapper.

## Acceptance Criteria

- [ ] projection over the divergent campaign is exact (6/6) once stamped
- [ ] never-downgrade preserves hand-run / unstamped complete subs
- [ ] skeleton drives ordering; missing campaign.md -> error
