# Plan Interview — 01-core (Backend Core & Claude Adapter)

## Session Info
- Date: 2026-04-10
- Split: 01-core
- Spec: webui/planning/01-core/spec.md (47 FRs)

## Decisions

### Claude Adapter packaging
- **Question:** Extract as own npm package or keep as module in server/src/core/?
- **Decision:** Module in server/src/core/
- **Rationale:** Simpler for V1, less setup overhead. Can extract later if reuse needed.

### Section count
- **Question:** 5-6 larger sections or 8-10 per FR-group?
- **Decision:** 8-10 sections (1 per FR group)
- **Rationale:** Natural boundaries, moderate size per section, better for parallel /shipwright-build.

## Context from Project Interview (carried forward)
- Hono (not Express) — DEC-001
- In-memory state from events — DEC-002
- task_created event type — DEC-003
- Phase dedup — DEC-004
- SSE over WebSocket — DEC-005
- Chat store — DEC-006
- Kanban-First UI pivot (UI acts as board consumer of these APIs)
