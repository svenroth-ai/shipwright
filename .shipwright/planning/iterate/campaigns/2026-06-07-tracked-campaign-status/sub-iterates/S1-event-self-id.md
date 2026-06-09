# Sub-Iterate: S1 — Event self-identification (campaign + sub_iterate_id stamp)

## Scope

Sub-iterate-runner passes --event-extras-json {"campaign":"<slug>","sub_iterate_id":"<id>"} to its F5b finalize (both values already in the brief). Expose manual /shipwright-iterate --campaign <slug> --sub-iterate-id <id> so a hand-run sub also stamps. The --event-extras-json hook already exists in finalize_iterate.py (idempotent per run_id). This is the load-bearing B-enabler: makes the events.jsonl self-sufficient so per-sub status can be projected without a 50%-unreliable slug heuristic.

## Acceptance Criteria

- [ ] work_completed events carry extras.campaign + extras.sub_iterate_id
- [ ] idempotent per run_id (re-run does not duplicate the event)
- [ ] manual --campaign / --sub-iterate-id flag path stamps the event
