---
campaign: 2026-06-07-tracked-campaign-status
status: draft
branch_strategy: stacked
created: 2026-06-07T20:29:15.989312+00:00
expands_triage: trg-fda5f7a3
---

# Campaign: 2026-06-07-tracked-campaign-status

## Intent

Durable producer-maintained campaign status (tracked SSoT)

WebUI reads per-sub campaign status from status.json, which is authoritative per the campaign-store.ts contract + PR #143 (producer-owned) — but it is untracked/never-committed, and the tracked campaign.md table is write-once 'pending' -> board is wrong on a fresh clone / deployed WebUI. RECOMMENDED: track status.json (per-tree commit + by-id SEMANTIC churn resolver, since it is a mutable object not an append-only log), mirroring the triage.jsonl/events.jsonl precedent -> ZERO WebUI change (status.json already authoritative). Plan-phase spike: derive status from the already-tracked events.jsonl instead (cleanest if the sub-iterate<->run_id<->event linkage is clean). REJECTED: promoting the campaign.md markdown table to status SSoT (contradicts the status.json-authoritative contract; would invert a 2-day-old WebUI contract; markdown-as-SSoT is the retired anti-pattern, cf. triage_inbox.md). Plan doc: .shipwright/planning/iterate/proposed-tracked-campaign-status.md. Surfaced by detective-realign C1/C2.

## Sub-Iterates

| ID | Slug | Title | Status |
|---|---|---|---|
| S1 | event-self-id | Event self-identification (campaign + sub_iterate_id stamp) | pending |
| S2 | status-projection | Projection + regenerate producer (regenerate_campaign_status) | pending |
| S3 | finalize-resolver | Finalize wiring + churn resolver (regenerate-on-conflict) | pending |
| S4 | backfill-docs | Backfill existing campaigns + docs | pending |
