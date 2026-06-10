# Sub-Iterate: S2 — Projection + regenerate producer (regenerate_campaign_status)

## Scope

New pure regenerate_campaign_status(campaign_dir, events_log): read campaign.md skeleton (ids/slugs/order/titles) + project events (extras.campaign==slug && extras.sub_iterate_id==id -> latest work_completed -> complete, carry commit/tests). Never-downgrade guard: status = max(committed, projected) over pending<in_progress<complete (failed/escalated explicit). Lifecycle recompute via the existing _all_subs_complete. Thin CLI wrapper.

> **S1 carry-forward (key shape):** the stamp keys live TOP-LEVEL on the
> event — read `event["campaign"]` / `event["sub_iterate_id"]`, NOT
> `event["extras"]["..."]`. F5b's `--event-extras-json` merges extras
> verbatim into the event object (no nested `extras` container).

## Acceptance Criteria

- [ ] projection over the divergent campaign is exact (6/6) once stamped
- [ ] never-downgrade preserves hand-run / unstamped complete subs
- [ ] skeleton drives ordering; missing campaign.md -> error
