# Shipwright Command Center — Interview Transcript

## Session Info
- Date: 2026-04-09/10
- Scope: Full Application
- Input: Spec/plan-shipwright-webui.md (detailed product plan)
- Session ID: webui-20260409-235310

---

## Interview Summary

### What is this project?
A **Command Center** (WebUI) for Shipwright — a local web application that provides a visual interface for managing multiple Shipwright projects in parallel. Inspired by Paperclip (MIT), adapted for the Shipwright SDLC pipeline. The user has one Command Center instead of 20 terminal windows. Projects run autonomously; the user is pulled in only when Claude needs a decision (Inbox pattern).

### Who is the target audience?
All Shipwright open-source users. Not absolute beginners, but also not requiring deep CLI expertise. "Replit light" — accessible for developers who have some experience. A Masterclass will be built around it. **The WebUI is the product** — users learn Shipwright through it.

### Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backend framework | **Hono** (NOT Express 5) | Modern, TypeScript-first, built-in SSE (`streamSSE()`), lightweight (~14KB). Better Masterclass appeal. Low risk on Node.js. |
| Frontend | React 19 + Vite 6 + TailwindCSS 4 + Radix UI | As specified in plan. Modern, accessible, well-supported. |
| Realtime | SSE (Server-Sent Events) | Single-user local app. Socket.io is overkill. Hono has native SSE support. |
| Task state storage | **In-memory from events + process tracking** | No tasks.json. Events = truth for completed tasks. Process manager = truth for running tasks. Server restart replays events. |
| New event type | **`task_created`** added to record_event.py | Enables task tracking from creation (not just completion). Orphan detection on crash (task_created without matching work_completed). |
| Chat history | WebUI stores alongside CLI sessions | NDJSON stream parsed AND persisted. Enables chat replay, task context switching, offline viewing. |
| Dual phase_completed events | Both plugin + orchestrator emit | WebUI deduplicates: prefers event with `detail` field. Backwards compatible, no orchestrator change needed. |
| CLI bridge | WebUI spawns Claude CLI directly | `claude --output-format stream-json --plugin-dir ...` as subprocess. Full control, plugins work via --plugin-dir. Paperclip approach. |
| Installation | `cd webui && npm install && npm run dev` | Standard Node.js. No Docker, no custom CLI wrapper. |
| Database | None (JSONL event log + JSON files) | Single-user local app. Event sourcing pattern. No SQLite/PGlite needed. |
| Auth | None | Local single-user application. |

### Critical Review of Original Plan

1. **Express 5 → Hono**: Express 5 is still maturing. Hono offers better TypeScript DX, built-in SSE, and is a better fit for a modern Masterclass product.

2. **tasks.json → In-memory**: The plan described a hybrid model with tasks.json as storage and events as truth. This creates a sync problem. Pure event-sourcing with in-memory state is cleaner.

3. **task_created event gap**: The plan had no event for task creation — only work_completed. Added task_created event type for full lifecycle tracking.

4. **Dual phase_completed**: All pipeline phases (project, design, plan, build, deploy, changelog) now emit their own phase_completed events (with --detail), alongside the orchestrator's generic phase_completed. Backend deduplicates in record_event.py; WebUI also handles deduplication client-side.

5. **Scope**: Plan said "no MVP splitting" — but it's a large project. We build iteratively (all features), but with clear technical splits for /shipwright-plan.

### Features Confirmed for V1
- Multi-Project Management (registry, wizard, parallel execution, process governor)
- Task System (event-driven, flat with virtual hierarchy, pipeline + iterate tasks)
- Inbox (aggregated questions, answer delivery via stdin, per-project and global)
- Chat (Claude Code-style, streaming, tool-call rendering, diff view)
- Smart File Viewer (type-specific renderers: Markdown, HTML preview, Mermaid, code, JSON)
- Claude CLI Adapter (subprocess management, NDJSON stream parsing, session management)
- IDE-Style Layout (5-panel: Rail + Sidebar + Chat + Viewer + Explorer)
- Toolbar + New Task Dialog (intent/complexity preview via existing Python scripts)
- Intent Detection Banner (non-blocking, in chat input area)
- File Explorer (slide-in, like Replit)
- Pipeline visualization (horizontal steps, section drawer)
- Project Wizard (step-by-step new project setup)

### Tech Stack Summary
```
Backend:  Hono (Node.js) + SSE + chokidar + node-cron + child_process.spawn
Frontend: React 19 + Vite 6 + TailwindCSS 4 + Radix UI + TanStack React Query
Chat:     react-markdown + remark-gfm + rehype-highlight + react-diff-viewer
Diagrams: Mermaid (compliance diagrams)
```
