# Sub-Iterate: S4 — Backfill existing campaigns + docs

## Scope

Verify existing campaigns' status.json (already tracked via the PR #168 stopgap) regenerate without downgrade. Docs: hooks-and-pipeline.md artifact-write matrix (status.json = tracked per-tree churn artifact, regenerate bucket), glossary.md, an ADR; cross-link reference_webui_campaign_status_tokens. Commit doc/data via the iterate flow. On campaign completion, dismiss the anchor trg-fda5f7a3 (campaign done).

## Acceptance Criteria

- [ ] existing campaigns' status.json regenerate without downgrade
- [ ] docs updated (hooks-matrix, glossary, ADR)
- [ ] token vocabulary SSoT documented (campaign_progress.LIFECYCLE_STATUSES + webui VALID_LIFECYCLE/VALID_STATUSES)
- [ ] anchor trg-fda5f7a3 dismissed (campaign done)
