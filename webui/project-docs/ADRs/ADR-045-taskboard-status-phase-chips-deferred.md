# ADR-045 — TaskBoard Status + Phase chip rows deferred to Phase C

- **Status:** Accepted
- **Date:** 2026-04-20
- **Scope:** webui iterate-3 remediation Phase B1 (TaskBoard visual rebuild)
- **Related:** ADR-044 (iterate 3 close-out), ADR-037 (projectId v2 schema)

## Context

The approved mockup `webui/designs/screens/kanban-with-projects.html` includes
two chip rows under the TaskBoard header:

1. **Status:** All / To do / Running / Done / Failed — mapped to `task.state`.
2. **Phase:** build / design / plan / test / deploy / compliance / security
   — mapped to a per-task `phase` field.

Phase B1's remediation plan asks either to (a) implement both chip rows against
`task.state` + `task.phase`, or (b) defer them to Phase C and ship the header
dropdown + view toggle only.

## Decision

**Defer both chip rows to Phase C.**

Reasons:

1. **Data model gap — Phase chips.** `ExternalTask`
   (`webui/client/src/lib/externalApi.ts`) has no `phase` field. `classifyPhase`
   exists in `webui/client/src/lib/classifyPhase.ts` but is scoped to
   `NewIssueModal` title-heuristics; it is not projected onto the persisted
   task row. Adding a per-task phase projection requires either (a) a server
   change to `sdk-sessions-store` v3 with a `phase` column + backfill rule, or
   (b) a client-side re-classification of every task on every render. Both are
   Phase-C scope (new data shape + migration), not a Phase-B visual rebuild.

2. **Semantic gap — Status chips.** `ExternalTask.state` has 7 members
   (`draft`, `awaiting_external_start`, `active`, `idle`, `jsonl_missing`,
   `launch_failed`, `done`). The mockup's 5-bucket Status filter collapses
   these into `To do` / `Running` / `Done` / `Failed`. That mapping is a UX
   decision with tradeoffs (e.g. where does `idle` go? `awaiting_external_start`
   maps to `To do` or `Running`?). It needs a product decision, not a visual
   rebuild.

3. **Scope discipline.** Phase B1 is bounded to "visual rebuild consuming
   Phase A tokens." Inventing a data projection mid-rebuild breaks the
   Phase-B rule "State wiring, hooks, queries, API contracts all STAY."

## Consequences

- Phase B1 ships the header (ProjectFilterDropdown + optional view toggle +
  Preview + Create split button) and the 3 kanban columns only.
- The filter-row `<div class="header-filters">` section of the mockup is
  **not** rendered. The search input with `/` hotkey is visually absent in B1.
- 70-e inbox project filter test continues to assert the inbox dropdown only
  (not TaskBoard).

## Rollback path to Phase C

Phase C (tentatively iterate 3.8) will:

1. Add `phase: TaskPhase | null` to `ExternalTask` server-side, derived at
   task-create time from `classifyPhase(title, description)` and stored in
   `sdk-sessions.json` schema v3. v2 rows lazy-upgrade on first read.
2. Add `StatusChipRow` + `PhaseChipRow` components under
   `webui/client/src/components/external/`, driven by `useTaskStatusCounts()`
   and `useTaskPhaseCounts()` selectors.
3. Mount both under the TaskBoard header (and optionally Inbox).
4. Extend the `/` search input with a real `useTaskSearchQuery` hook + URL
   param.

No code in Phase B1 pre-commits to this design — we can still pick a different
shape in Phase C.

## Non-goals

- This ADR does not commit the schema-v3 upgrade path; that's Phase C's call.
- This ADR does not block Phase B1 shipping without the chip rows.
