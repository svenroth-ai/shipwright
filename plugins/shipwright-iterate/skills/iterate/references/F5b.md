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

**The finalize FR-gate (ADR-059) is enforced on this path** (since
`iterate-2026-06-05-fr-linkage-lifecycle`): the event is **rejected before
write** — finalize exits non-zero with guidance — unless it is classified. Set
**exactly one** of the two branches and **omit** the other keys; a leftover
placeholder such as `"change_type": "{docs|…}"` is itself a rejection (a present
`change_type` must be a recognized value paired with a valid `none_reason`):

- **FR-linked** (feature/change touching the spec) — set `affected_frs` and/or
  `new_frs`; **omit** `change_type`/`none_reason`.
- **No-FR** (docs/tooling/compliance/infra) — set `change_type` ∈
  `{docs,tooling,compliance,infra}` + a one-line `none_reason`; **omit**
  `affected_frs`/`new_frs`.

```bash
# Example: FR-linked iterate. For a no-FR iterate, drop affected_frs/new_frs
# and instead set "change_type" + "none_reason" (see the two branches above).
extras='{
  "intent": "{feature|change|bug}",
  "description": "{short_description}",
  "spec_impact": "{add|modify|remove|none}",
  "spec_impact_justification": "{required when spec_impact=none}",
  "affected_frs": ["FR-..."],
  "new_frs": ["FR-..."],
  "tests": {"passed": N, "total": N, "e2e_run": true}
}'
uv run "{shared_root}/scripts/tools/finalize_iterate.py" \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --reason "iterate: {short_description}" \
  --event-extras-json "$extras"
```

**Campaign identity stamp (campaign 2026-06-07-tracked-campaign-status, S1):**
when the iterate is a campaign sub-iterate — spawned by the autonomous loop OR
hand-run via `--campaign <slug> --sub-iterate-id <id>` — add two extra keys to
the same `--event-extras-json` object: `"campaign": "<campaign-slug>"` and
`"sub_iterate_id": "<id>"`. They are additive metadata (merged verbatim,
idempotent per run_id like the rest of the event) and do NOT replace the
FR-gate classification above. The stamp makes `shipwright_events.jsonl`
self-sufficient for per-sub-iterate status projection — no slug-join
heuristics against branch names.

> **Step 6 — per-tree campaign board (campaign 2026-06-07, S3).** When the
> `campaign` stamp is present, `finalize_iterate` re-projects
> `.shipwright/planning/iterate/campaigns/<slug>/status.json` from this
> worktree's event log (the canonical `campaign_status` producer — byte-identical
> to the `campaign_progress regenerate` CLI) and writes it into the worktree, so
> **F6 stages it** and the producer-owned board ships in the PR. This replaces
> the old write-once main-tree file; the autonomous-loop 3g main-tree
> `campaign_progress update-status` is demoted to a local-board convenience.
> Best-effort + no-op for a non-campaign iterate. Reads back at
> `result["steps"]["campaign_status"]`.

Reads back: `result["steps"]["event"]["id"]` — capture it so F6 can confirm
the event is present before staging `shipwright_events.jsonl` (and for the
legacy F6.5 SHA patch, used only by non-worktree callers).

The script is idempotent per `run_id` — re-invocations return the
existing event_id rather than recording a duplicate. If you skip this
step, the Stop hook will run it automatically as a fallback when the
session ends — but **without** the event_extras, so the enforced FR-gate
**rejects that fallback write** (it would be an unclassified event): nothing
is recorded and the failure is logged to stderr. For a clean F11 you **must**
call F5b yourself with the full metadata.

> **Note:** F7 (separate `record_event.py` call) is REPLACED by F5b (event
> recording into the worktree log) + F6 (staging it into the commit). The
> historical F7 / F7b are kept for the rare out-of-band case (event replay,
> non-worktree phases) — NOT needed for a normal worktree iterate, where the
> event already ships in the PR.
