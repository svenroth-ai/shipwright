# Sub-Iterate: D1 — Gitignored per-tree outbox + reroute background producers + shared-reader union

## Scope

Introduce per-tree `.shipwright/triage.outbox.jsonl` (GITIGNORED, never tracked -> no leak-guard, no pull-block, no main drift). Reroute the 3 background producers (plugin-sync Stop-hook, compliance audit, `triage_add` WHEN invoked in the main tree) to append to the outbox, NOT the tracked log. Worktree/PR-branch writes still go straight to the tracked `triage.jsonl` (they already ship via the PR). Extend the shared reader (`triage.read_all_items` / SSoT) to return tracked UNION outbox so Python consumers (RTM, compliance) see background findings immediately.

## Acceptance Criteria

- [ ] A background-producer append lands in `triage.outbox.jsonl`, NOT the tracked `triage.jsonl` (tracked file stays clean -> no main drift)
- [ ] `triage.read_all_items` returns tracked UNION outbox (background finding visible same-session)
- [ ] outbox is gitignored (never tracked)
- [ ] a worktree / PR-branch `triage_add` still writes the tracked log directly
