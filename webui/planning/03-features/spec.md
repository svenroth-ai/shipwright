# Viewers, Explorer, Wizard & Advanced Features

> Split 03 of 03 | Source: Spec/plan-shipwright-webui.md

## 1. Purpose & Scope

Build the specialized viewers, file explorer, project wizard, and advanced interaction features that integrate into the Kanban-first board UI defined in Split 02. This split adds rich content rendering inside Task Detail views, project creation, issue management, and background intelligence features to the Command Center.

**In Scope:**
- Smart File Viewer rendered inside Task Detail view (right panel)
- File Explorer as a slide-in inside Task Detail view
- Project Wizard (4-step creation flow; project appears as board tab)
- New Issue Dialog with background auto-classification
- Intent Detection hint inside Task Detail chat (lower priority)
- Global Inbox full-page view
- Settings page (global + per-project + phase-to-status mapping)

**Out of Scope:**
- Backend APIs (Split 01: docs, classify, settings, inbox routes)
- Layout shell, panel resizing, Rail, Sidebar, Chat engine (Split 02)
- Terminal/xterm.js fallback (future iteration)
- Telegram/Slack webhook delivery (future iteration)
- Monaco Editor or full code editing (read-only viewers only)

## 2. Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-03.01 | The system SHALL display multiple open files as tabs in the Smart Viewer (rendered inside the Task Detail right panel), allowing the user to open, close, and switch between tabs | Must |
| FR-03.02 | The system SHALL render Markdown files using remark-gfm with Mermaid diagram support | Must |
| FR-03.03 | The system SHALL render HTML files from `designs/` as iframe previews | Must |
| FR-03.04 | The system SHALL render TypeScript/TSX files with syntax highlighting via rehype-highlight | Must |
| FR-03.05 | The system SHALL render JSON files as a collapsible tree view with expand/collapse per node | Must |
| FR-03.06 | The system SHALL render `spec.md` files with FR status badges (pass/fail/pending) derived from event data | Should |
| FR-03.07 | The system SHALL render `plan.md` files with a section progress overlay showing completion status per section | Should |
| FR-03.08 | The system SHALL render `*_consistency_report.json` files as a consistency dashboard with a table showing pass/warn/fail per category | Should |
| FR-03.09 | The system SHALL render Mermaid diagrams inline for files under `compliance/` | Must |
| FR-03.10 | The system SHALL display external URLs (e.g., localhost:3000, Playwright reports) as iframe tabs in the Smart Viewer | Must |
| FR-03.11 | The system SHALL provide a slide-in File Explorer inside the Task Detail view with a recursive directory tree supporting expand/collapse of directories | Must |
| FR-03.12 | The system SHALL display git status indicators (M/A/D) per file in the File Explorer, matching VSCode conventions | Must |
| FR-03.13 | The system SHALL filter the File Explorer to show only relevant directories: src/, planning/, designs/, agent_docs/, compliance/ | Must |
| FR-03.14 | The system SHALL open a file in the Smart Viewer when the user clicks it in the File Explorer | Must |
| FR-03.15 | The system SHALL provide a 4-step Project Wizard modal for creating new projects (Name/Directory/Description, Stack Profile/Autonomy, Environment Variables, Confirmation) | Must |
| FR-03.16 | The system SHALL validate that the selected project directory exists before allowing the wizard to proceed past Step 1 | Must |
| FR-03.17 | The system SHALL register the new project, add it as a new tab on the Kanban board, and automatically start the pipeline after wizard completion | Must |
| FR-03.18 | The system SHALL provide a New Issue Dialog (modal) with Title and Description fields. On submit, the card SHALL appear immediately in the Backlog column of the Kanban board | Must |
| FR-03.18a | The system SHALL run auto-classification (intent, complexity, risk flags, affected FRs) as a background process via POST /api/projects/:id/classify after issue creation, and enrich the card with results when available | Must |
| FR-03.19 | The system SHALL spawn a Claude CLI process with `/shipwright-iterate --type {detected_type}` when the user moves an issue to In Progress or explicitly triggers "Start Task" on a card | Must |
| FR-03.20 | The system MAY display a non-blocking Intent Detection hint inside the Task Detail chat when a typed message is classified as a code change with confidence >= 0.7 | May |
| FR-03.21 | The system SHALL skip intent detection for slash commands, questions containing "?", greetings, and messages shorter than 10 characters | Should |
| FR-03.22 | The system SHALL provide a Global Inbox view that aggregates all open questions across all projects, showing project name, task context, question text, option buttons, and a freetext input | Must |
| FR-03.23 | The system SHALL deliver inbox answers via POST /api/inbox/:id/answer when the user responds to a question | Must |
| FR-03.23a | The system SHALL provide a Projects page listing all registered projects with name, status (active/paused), last activity timestamp, and current phase progress | Must |
| FR-03.23b | The system SHALL allow navigating from the Projects page to a project's Task Board (filtered) or project Settings | Must |
| FR-03.24 | The system SHALL provide a Settings page with global settings (port, max concurrent processes, default autonomy) and per-project settings (profile, autonomy, environment variables) | Must |
| FR-03.26 | The system SHALL allow users to configure the phase-to-status mapping for each project in Settings (which Shipwright phases map to which Kanban columns: Backlog, In Progress, In Review, Done) | Must |
| FR-03.25 | The system SHOULD populate the Project Wizard Step 3 (Environment Variables) dynamically based on the selected stack profile from Step 2 | Should |

### Acceptance Criteria

**FR-03.01: Tab Management**
- [ ] User can open a file and it appears as a new tab in the Smart Viewer
- [ ] User can close individual tabs via a close button on each tab
- [ ] User can switch between open tabs by clicking on them
- [ ] Opening an already-open file activates its existing tab instead of creating a duplicate

**FR-03.02: Markdown Rendering**
- [ ] GFM tables, task lists, and strikethrough render correctly
- [ ] Mermaid code blocks (```mermaid) render as SVG diagrams
- [ ] Links within Markdown are clickable and open in the viewer or externally as appropriate

**FR-03.03: HTML iframe Preview**
- [ ] Files matching `designs/*.html` render inside a sandboxed iframe
- [ ] The iframe fills the available viewer space and is responsive

**FR-03.04: Syntax Highlighting**
- [ ] `.ts` and `.tsx` files display with language-appropriate syntax highlighting
- [ ] Line numbers are visible alongside the code

**FR-03.05: JSON Tree View**
- [ ] JSON files render as an interactive tree with collapsible nodes
- [ ] All nodes are collapsed by default except the root level
- [ ] Expanding a node reveals its children; collapsing hides them
- [ ] Invalid JSON displays a clear error message instead of crashing

**FR-03.09: Compliance Mermaid Rendering**
- [ ] Files under `compliance/` containing Mermaid code blocks render diagrams inline
- [ ] Non-Mermaid content in compliance files renders as standard Markdown

**FR-03.10: External URL Tabs**
- [ ] User can open a localhost URL as a tab in the Smart Viewer
- [ ] The external page renders inside an iframe within the tab
- [ ] Playwright HTML reports are viewable as external URL tabs

**FR-03.11: File Explorer Tree**
- [ ] The File Explorer slides in inside the Task Detail view when toggled
- [ ] Directories display as expandable/collapsible nodes
- [ ] Files display as leaf nodes with appropriate file-type icons
- [ ] The explorer is hidden by default

**FR-03.12: Git Status Indicators**
- [ ] Modified files show an "M" indicator
- [ ] Added (untracked/staged) files show an "A" indicator
- [ ] Deleted files show a "D" indicator
- [ ] Files with no git changes show no indicator

**FR-03.13: Directory Filtering**
- [ ] Only src/, planning/, designs/, agent_docs/, and compliance/ directories are shown
- [ ] Other directories (e.g., node_modules/, .git/) are excluded from the tree

**FR-03.14: Click-to-Open**
- [ ] Clicking a file in the File Explorer opens it in the Smart Viewer
- [ ] The correct renderer is selected based on the file path and extension

**FR-03.15: Project Wizard Steps**
- [ ] Step 1 collects project name, directory path (with browse capability), and description
- [ ] Step 2 offers stack profile selection and autonomy level (Guided/Autonomous)
- [ ] Step 3 shows environment variable fields appropriate to the selected profile
- [ ] Step 4 displays a confirmation summary of all entered data
- [ ] User can navigate back to previous steps to edit

**FR-03.16: Directory Validation**
- [ ] The wizard validates that the entered directory path exists on the filesystem
- [ ] An inline error message appears if the directory does not exist
- [ ] The "Next" button is disabled until the directory is valid

**FR-03.17: Project Registration + Pipeline Start**
- [ ] After confirmation, the project is added to the project registry
- [ ] The project appears as a new tab on the Kanban board
- [ ] The pipeline starts automatically and the first phase begins

**FR-03.18: New Issue Dialog**
- [ ] The dialog shows Title and Description fields
- [ ] On submit, a new card appears immediately in the Backlog column
- [ ] The dialog closes after issue creation

**FR-03.18a: Background Auto-Classification**
- [ ] After issue creation, auto-classification runs in the background via POST /api/projects/:id/classify
- [ ] Intent (bug/feature/change), complexity (small/medium/large), risk flags, and affected FRs are written to the card when available
- [ ] The card visually updates (badges appear) without user interaction
- [ ] If classification fails, the card remains usable without enrichment data

**FR-03.19: Start Task Action**
- [ ] Moving a card to In Progress or clicking "Start Task" spawns a Claude CLI process with the detected type
- [ ] The card status updates to "running" immediately
- [ ] If no classification result is available yet, the system prompts the user for task type

**FR-03.20: Intent Detection Hint (Task Detail Chat)**
- [ ] A subtle hint appears inside the Task Detail chat input when confidence >= 0.7
- [ ] The hint shows the detected intent and confidence score
- [ ] The hint is dismissible and non-blocking

**FR-03.21: Intent Detection Guards**
- [ ] Messages starting with "/" are not classified
- [ ] Messages containing "?" are not classified
- [ ] Messages shorter than 10 characters are not classified
- [ ] Common greetings (e.g., "hi", "hello", "hey") are not classified

**FR-03.22: Global Inbox View**
- [ ] All open questions from all projects are displayed in a single view
- [ ] Each item shows: project name, task context, question text, and answer options
- [ ] Items are visually grouped by project

**FR-03.23: Inbox Answer Delivery**
- [ ] Clicking an option button sends the answer via POST /api/inbox/:id/answer
- [ ] Typing freetext and submitting sends the freetext answer via the same endpoint
- [ ] Answered items are removed from the inbox view

**FR-03.24: Settings Page**
- [ ] Global settings (port, max concurrent processes, default autonomy) are editable and persist
- [ ] Per-project settings (profile, autonomy, environment variables) are editable and persist
- [ ] Changes take effect without requiring a server restart

**FR-03.26: Phase-to-Status Mapping**
- [ ] Settings page shows a per-project section for mapping Shipwright phases to Kanban columns (Backlog, In Progress, In Review, Done)
- [ ] Each phase can be assigned to exactly one column
- [ ] A sensible default mapping is provided for new projects
- [ ] Changes to the mapping immediately update the board column placement of existing cards

## 3. Quality Requirements

| ID | Requirement | Category |
|----|-------------|----------|
| QR-03.01 | The system SHALL render Markdown files of up to 5000 lines without visible lag (< 500ms to first paint) | Performance |
| QR-03.02 | The system SHALL render Mermaid diagrams within 2 seconds for diagrams with up to 50 nodes | Performance |
| QR-03.03 | The system SHALL debounce classify API calls at 500ms for Intent Detection hints to avoid excessive backend load. Background auto-classification after issue creation fires once (no debounce needed) | Performance |
| QR-03.04 | The system SHALL sanitize all HTML rendered in iframes to prevent script injection from design files affecting the host application | Security |
| QR-03.05 | The system SHALL ensure all interactive components (tabs, tree nodes, buttons, form fields) are keyboard-navigable and have appropriate ARIA attributes | Accessibility |

## 4. Constraints

| ID | Constraint | Type |
|----|-----------|------|
| C-03.01 | Must use Radix UI primitives for all modals, dialogs, and interactive components (consistency with Split 02) | Technical |
| C-03.02 | Must use react-markdown + remark-gfm + rehype-highlight for Markdown/code rendering (no Monaco Editor) | Technical |
| C-03.03 | Must use existing classify_intent.py and classify_complexity.py scripts via the classify API — no classification logic duplication in the frontend | Technical |
| C-03.04 | Must use TanStack React Query for all data fetching and cache invalidation (consistency with Split 02) | Technical |
| C-03.05 | The File Explorer must only display read-only views — no file creation, editing, or deletion | Functional |

## 5. Dependencies

**Depends on:**
- Split 01 (Backend Core): docs API (GET /api/projects/:id/docs — file tree + content), classify API (POST /api/projects/:id/classify), settings API (GET/PUT /api/settings), inbox API (GET /api/inbox, POST /api/inbox/:id/answer), projects API (POST /api/projects for wizard registration)
- Split 02 (UI Shell): Kanban board layout with Task Detail right panel (hosts viewer + explorer + chat), component patterns (Radix UI conventions, TanStack Query hooks), Board toolbar with "New Issue" button trigger

**Provides to:**
- Nothing (final split)

**Dependency type:** APIs, patterns

## 6. Key Decisions

- **Decision:** Smart Viewer lives inside Task Detail view (right panel) — not as a permanent top-level panel
  **Rationale:** With the Kanban-first layout, the board is the primary view. File viewing is contextual to a task, so it belongs inside the task detail rather than occupying permanent screen space.

- **Decision:** File Explorer is a slide-in inside Task Detail view, hidden by default
  **Rationale:** Files are browsed in the context of a specific task. Embedding the explorer inside the task detail keeps navigation task-scoped rather than global.

- **Decision:** New Issue Dialog is minimal (Title + Description only); classification runs in the background after creation
  **Rationale:** Reduces friction for issue creation. Users want to capture ideas quickly. Auto-classification enriches the card asynchronously, so the card is useful immediately and gets smarter over time.

- **Decision:** New Issue Dialog reuses existing Python classify scripts via the backend API (as background enrichment)
  **Rationale:** classify_intent.py and classify_complexity.py already implement the detection logic for the CLI. Running them post-creation avoids blocking the dialog on API latency.

- **Decision:** Intent Detection downgraded from Must to May; now scoped to Task Detail chat
  **Rationale:** With Kanban-first, there is no global chat input. Intent detection can still add value inside a task's chat, but it is lower priority since tasks are already explicitly scoped.

- **Decision:** Project Wizard validates directory existence, not directory emptiness
  **Rationale:** Users may want to add Shipwright to an existing project directory that already contains files.

- **Decision:** No file editing in the viewer or explorer — strictly read-only
  **Rationale:** Claude handles all code changes. The viewer is for inspection and review, not manual editing. This avoids conflicts with Claude's file operations.

## 7. UI Requirements

| Screen | Description | Key Elements |
|--------|-------------|-------------|
| Smart File Viewer | Tabbed viewer rendered inside the Task Detail right panel. Each tab renders content with a type-specific renderer. | Tab bar (scrollable if many tabs), close button per tab, active tab highlight, renderer area below tabs |
| File Explorer | Slide-in panel inside the Task Detail view. Shows a filtered directory tree for the task's project. | Toggle button (toolbar icon inside task detail), recursive tree with indent guides, file/folder icons, git status badges (M/A/D), expand/collapse chevrons |
| Project Wizard | Full-screen modal with 4 sequential steps. Progress indicator at top. Back/Next/Start navigation at bottom. Project appears as a new board tab on completion. | Step indicator (1-2-3-4), form fields per step, directory browse button, radio buttons for profile/autonomy, key-value pairs for env vars, confirmation summary |
| New Issue Dialog | Compact modal triggered from board toolbar. Title and Description fields only. Card appears in Backlog immediately; enrichment arrives asynchronously. | Title input (autofocused), Description textarea, "Create" and "Cancel" buttons |
| Intent Detection Hint | Subtle inline hint inside Task Detail chat input. Appears when classification confidence >= 0.7. Lower priority (MAY). | Intent label with confidence score, dismissible, non-blocking |
| Global Inbox | Full-page view replacing the main content area. Lists all open questions grouped by project. | Project group headers, question cards with context excerpt, option buttons (from AskUserQuestion), freetext input with submit, empty state when no questions |
| Settings Page | Full-page view with three sections: Global, Per-Project, and Phase-to-Status Mapping. Tab or accordion layout. | Global section: port input, concurrency slider/input, autonomy radio. Per-project section: project selector dropdown, profile dropdown, autonomy radio, env var key-value editor. Phase mapping section: drag-or-select phases into Kanban columns. Save button |

**Layout preference:** Kanban-first (inherits from Split 02 shell)

### Screen Details

**Project Wizard — Step Flow:**
```
Step 1/4: Project
  Name:        [___________________]
  Directory:   [___________________] [Browse]
  Description: [___________________]
                                     [Next ->]

Step 2/4: Stack
  Profile:   (o) Supabase + Next.js  ( ) Custom
  Autonomy:  (o) Guided  ( ) Autonomous
                            [<- Back] [Next ->]

Step 3/4: Environment
  NEXT_PUBLIC_SUPABASE_URL:  [___________________]
  SUPABASE_ANON_KEY:         [___________________]
  JELASTIC_TOKEN:            [___________________] (optional)
                            [<- Back] [Next ->]

Step 4/4: Confirmation
  Name:      My SaaS App
  Directory: ~/projects/my-app
  Profile:   Supabase + Next.js
  Autonomy:  Guided
  Env vars:  3 configured
                            [<- Back] [Start ->]
```

**New Issue Dialog:**
```
+------------------------------------------+
|  New Issue                           [x] |
|                                          |
|  Title:                                  |
|  [Fix the auth redirect bug         ]   |
|                                          |
|  Description:                            |
|  [Users are redirected to /login     ]   |
|  [after successful OAuth callback.   ]   |
|                                          |
|  [Create]                  [Cancel]      |
+------------------------------------------+
```

*After creation, the card appears in Backlog. Background enrichment adds badges:*
```
+---------------------------+
| Fix the auth redirect bug |
| bug · small · 1 risk      |
| FR-01.03                  |
+---------------------------+
```

**Intent Detection Hint (inside Task Detail chat):**
```
[Chat input field...]
  ╰─ Hint: looks like a "bug" (0.85) — [dismiss]
```

**Consistency Dashboard (renderer for *_consistency_report.json):**
```
| Category        | Status | Details          |
|-----------------|--------|------------------|
| FR Coverage     | PASS   | 12/12 covered    |
| Test Coverage   | WARN   | 89% (target 90%) |
| Spec Alignment  | PASS   | All aligned      |
| Design Sync     | FAIL   | 2 screens stale  |
```

## 8. References

- Requirements: `Spec/plan-shipwright-webui.md`
- Interview: `webui/planning/shipwright_project_interview.md`
- Project Manifest: `webui/planning/project-manifest.md`
- Related splits: `webui/planning/01-core/spec.md`, `webui/planning/02-ui-shell/spec.md`
- Component library: Radix UI (https://www.radix-ui.com/)
- Markdown rendering: react-markdown + remark-gfm + rehype-highlight
- Mermaid rendering: mermaid (https://mermaid.js.org/)
