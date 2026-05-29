# F5b — Finalize Iterate Artifacts

Run **one** script that records the iterate's `work_completed` event,
regenerates compliance MDs, refreshes the build dashboard, and writes
the session handoff. Per
iterate-2026-05-23-compliance-md-single-producer the event is recorded
BEFORE the compliance regen so the regenerated MDs include the
iterate's own event — making the F6 commit snapshot self-consistent
(and eliminating the recurring E1-E5 staleness class).

`--event-extras-json` carries the SKILL.md F7-mandated fields (intent,
spec_impact, affected_frs/new_frs/change_type/none_reason, description,
changed_files). The event is recorded into **this worktree's own**
`shipwright_events.jsonl` (the per-tree, PR-committed model — see
events_log history, iterate-2026-05-29-events-jsonl-worktree-commit), with
`commit=""` since the F6 commit hasn't happened yet. **F6 stages
`shipwright_events.jsonl`** so the event ships in the iterate PR and merges to
`main` like every other artifact; the main tree is never written. The event
keeps `commit=""` (F6.5 SHA patch is skipped in the worktree flow — the
`Run-ID:` commit footer and `adr_id == run_id` carry the linkage).

```bash
extras='{
  "intent": "{feature|change|bug}",
  "description": "{short_description}",
  "spec_impact": "{add|modify|remove|none}",
  "spec_impact_justification": "{required when spec_impact=none}",
  "affected_frs": ["FR-..."],
  "new_frs": ["FR-..."],
  "change_type": "{docs|tooling|compliance|infra}",
  "none_reason": "{required when affected_frs/new_frs empty}",
  "tests": {"passed": N, "total": N, "e2e_run": true}
}'
uv run "{shared_root}/scripts/tools/finalize_iterate.py" \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --reason "iterate: {short_description}" \
  --event-extras-json "$extras"
```

Reads back: `result["steps"]["event"]["id"]` — capture it so F6 can confirm
the event is present before staging `shipwright_events.jsonl` (and for the
legacy F6.5 SHA patch, used only by non-worktree callers).

The script is idempotent per `run_id` — re-invocations return the
existing event_id rather than recording a duplicate. If you skip this
step, the Stop hook will run it automatically as a fallback when the
session ends (but without the event_extras — for a clean F11 you must
call F5b yourself with the full metadata).

> **Note:** F7 (separate `record_event.py` call) is REPLACED by F5b (event
> recording into the worktree log) + F6 (staging it into the commit). The
> historical F7 / F7b are kept for the rare out-of-band case (event replay,
> non-worktree phases) — NOT needed for a normal worktree iterate, where the
> event already ships in the PR.
