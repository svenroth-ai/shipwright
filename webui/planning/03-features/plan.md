# Implementation Plan — Viewers, Explorer, Wizard & Advanced Features

## Overview

This plan covers the final frontend layer of the Shipwright Command Center: specialized content viewers, a file explorer, the project creation wizard, issue enrichment, and supporting pages (projects list, global inbox, settings). All components integrate into the Kanban-first layout established in Split 02 — the Smart Viewer and File Explorer live inside the Task Detail right panel, the Project Wizard and New Issue enrichment extend existing board interactions, and the three full-page views (Projects, Inbox, Settings) slot into the sidebar navigation.

The implementation is organized into 7 sections in dependency order. Section 01 builds the Smart Viewer shell with tab management and the Markdown renderer (the most reused renderer). Section 02 adds all remaining renderers (HTML iframe, JSON tree, spec/plan overlays, consistency dashboard, compliance Mermaid, external URL tabs). Section 03 implements the File Explorer slide-in with directory tree, git status indicators, and click-to-open integration with the viewer. Section 04 builds the 4-step Project Wizard modal. Section 05 extends the New Issue Dialog with background auto-classification and card enrichment animation. Section 06 implements the three full-page views (Projects list, Global Inbox, Settings with phase-to-status mapping). Section 07 adds the optional Intent Detection hint inside Task Detail chat.

The TDD approach uses Vitest + @testing-library/react for component tests, renderHook for custom hook tests, and MSW for API mocking. Every renderer is tested with representative fixture data. Interactive components verify keyboard navigation and ARIA attributes. Tests are co-located with source files per project conventions.

**Key patterns:**
- TanStack React Query as single data layer — all file content, classification results, and settings fetched through query hooks
- Radix UI primitives for modals (Dialog), tree views (Collapsible), tabs (Tabs), and form elements
- TailwindCSS 4 utility classes with AI Portal brand tokens
- react-markdown + remark-gfm + rehype-highlight for Markdown/code rendering (C-03.02)
- mermaid library for diagram rendering (lazy-loaded)
- Component files under 300 lines, decomposed into subcomponents when larger
- All viewers are strictly read-only (C-03.05)

## SECTION_MANIFEST
```yaml
sections:
  - id: "01"
    name: "smart-viewer"
    title: "Smart Viewer — Tab Management, Router & Markdown Renderer"
    depends_on: []
    frs: ["FR-03.01", "FR-03.02", "FR-03.03", "FR-03.05", "FR-03.09"]
  - id: "02"
    name: "viewer-renderers"
    title: "Viewer Renderers — HTML, JSON, Overlays, Dashboard & URLs"
    depends_on: ["01"]
    frs: ["FR-03.04", "FR-03.06", "FR-03.07", "FR-03.08", "FR-03.10"]
  - id: "03"
    name: "file-explorer"
    title: "File Explorer — Directory Tree, Git Status & Click-to-Open"
    depends_on: ["01"]
    frs: ["FR-03.11", "FR-03.12", "FR-03.13", "FR-03.14"]
  - id: "04"
    name: "project-wizard"
    title: "Project Wizard — 4-Step Creation Flow"
    depends_on: []
    frs: ["FR-03.15", "FR-03.16", "FR-03.17"]
  - id: "05"
    name: "new-issue-dialog"
    title: "New Issue Dialog — Enrichment Animation & Classify Integration"
    depends_on: []
    frs: ["FR-03.18", "FR-03.18a", "FR-03.19"]
  - id: "06"
    name: "projects-inbox-settings"
    title: "Projects List, Global Inbox & Settings Pages"
    depends_on: []
    frs: ["FR-03.22", "FR-03.23", "FR-03.23a", "FR-03.23b", "FR-03.24", "FR-03.25", "FR-03.26"]
  - id: "07"
    name: "intent-detection"
    title: "Intent Detection Hint (Task Detail Chat)"
    depends_on: []
    frs: ["FR-03.20", "FR-03.21"]
```

## Sections

---

### Section 01: Smart Viewer — Tab Management, Router & Markdown Renderer
**Goal:** Build the Smart Viewer shell inside the Task Detail right panel with a tab bar for managing open files, a content-type router that selects the appropriate renderer, and the Markdown renderer (remark-gfm + Mermaid). This section establishes the viewer architecture that all subsequent renderers plug into.

**FRs:** FR-03.01, FR-03.02, FR-03.09

**Files:**
- `client/src/components/viewer/SmartViewer.tsx` — tab bar + active renderer area
- `client/src/components/viewer/ViewerTabBar.tsx` — scrollable tab bar with close buttons
- `client/src/components/viewer/ViewerRouter.tsx` — routes file path/type to correct renderer
- `client/src/components/viewer/renderers/MarkdownRenderer.tsx` — react-markdown + remark-gfm + rehype-highlight
- `client/src/components/viewer/renderers/MermaidBlock.tsx` — Mermaid diagram rendering (lazy)
- `client/src/hooks/useViewerTabs.ts` — tab state management (open, close, activate, deduplicate)
- `client/src/hooks/useFileContent.ts` — TanStack Query hook for GET /api/projects/:id/docs?path=...
- `client/src/types/viewer.ts` — ViewerTab, FileType, RendererProps interfaces

**Depends on:** Split 02 Section 07 (Task Detail layout with viewer slot)

---

### Section 02: Viewer Renderers — HTML, JSON, Overlays, Dashboard & URLs
**Goal:** Implement the remaining content-type renderers that plug into the Smart Viewer router: syntax-highlighted code, HTML iframe preview, JSON tree view, spec FR badge overlay, plan section progress overlay, consistency dashboard table, and external URL iframe tabs.

**FRs:** FR-03.04, FR-03.06, FR-03.07, FR-03.08, FR-03.10

**Files:**
- `client/src/components/viewer/renderers/CodeRenderer.tsx` — syntax highlighting with rehype-highlight + line numbers
- `client/src/components/viewer/renderers/HtmlPreviewRenderer.tsx` — sandboxed iframe for design HTML
- `client/src/components/viewer/renderers/JsonTreeRenderer.tsx` — collapsible tree view
- `client/src/components/viewer/renderers/SpecOverlayRenderer.tsx` — Markdown + FR status badges
- `client/src/components/viewer/renderers/PlanOverlayRenderer.tsx` — Markdown + section progress bars
- `client/src/components/viewer/renderers/ConsistencyDashboard.tsx` — table with pass/warn/fail
- `client/src/components/viewer/renderers/ExternalUrlRenderer.tsx` — iframe for localhost URLs

**Depends on:** Section 01 (viewer shell + router)

---

### Section 03: File Explorer — Directory Tree, Git Status & Click-to-Open
**Goal:** Build a slide-in File Explorer inside the Task Detail view with a recursive directory tree, git status indicators (M/A/D), directory filtering to relevant paths, and click-to-open integration with the Smart Viewer tabs.

**FRs:** FR-03.11, FR-03.12, FR-03.13, FR-03.14

**Files:**
- `client/src/components/explorer/FileExplorer.tsx` — slide-in panel with toggle
- `client/src/components/explorer/DirectoryTree.tsx` — recursive tree with expand/collapse
- `client/src/components/explorer/TreeNode.tsx` — single node (file or directory)
- `client/src/components/explorer/GitStatusBadge.tsx` — M/A/D indicator
- `client/src/hooks/useFileTree.ts` — TanStack Query hook for GET /api/projects/:id/docs (tree)
- `client/src/types/explorer.ts` — FileTreeNode, GitStatus interfaces

**Depends on:** Section 01 (useViewerTabs for click-to-open), Split 02 Section 07 (explorer slot in Task Detail)

---

### Section 04: Project Wizard — 4-Step Creation Flow
**Goal:** Build a full-screen modal wizard for creating new projects with four steps: Name/Directory/Description, Stack Profile/Autonomy, Environment Variables, and Confirmation. Validates directory existence, registers the project via POST /api/projects, adds the project as a new board tab, and starts the pipeline.

**FRs:** FR-03.15, FR-03.16, FR-03.17

**Files:**
- `client/src/components/wizard/ProjectWizard.tsx` — modal shell with step indicator and navigation
- `client/src/components/wizard/steps/ProjectInfoStep.tsx` — Step 1: name, directory, description
- `client/src/components/wizard/steps/StackProfileStep.tsx` — Step 2: profile selection, autonomy radio
- `client/src/components/wizard/steps/EnvVarsStep.tsx` — Step 3: key-value env var editor
- `client/src/components/wizard/steps/ConfirmationStep.tsx` — Step 4: summary review
- `client/src/components/wizard/StepIndicator.tsx` — 4-step progress indicator
- `client/src/hooks/useCreateProject.ts` — TanStack Query mutation for POST /api/projects
- `client/src/hooks/useValidateDirectory.ts` — debounced directory validation hook

**Depends on:** Split 02 Section 03 (data hooks pattern)

---

### Section 05: New Issue Dialog — Enrichment Animation & Classify Integration
**Goal:** Extend the New Issue Dialog (basic modal from Split 02 Section 05) with background auto-classification via POST /api/projects/:id/classify after issue creation, and a card enrichment animation that shows badges appearing when classification results arrive. Also wire the "Start Task" action to spawn Claude CLI with detected type.

**FRs:** FR-03.18, FR-03.18a, FR-03.19

**Files:**
- `client/src/components/board/CardEnrichment.tsx` — badge appearance animation on card
- `client/src/hooks/useClassifyTask.ts` — TanStack Query mutation for POST /api/projects/:id/classify
- `client/src/hooks/useStartTask.ts` — mutation to trigger Claude CLI spawn with detected type
- `client/src/components/board/StartTaskButton.tsx` — "Start Task" button on card/detail

**Depends on:** Split 02 Section 05 (New Issue modal), Split 02 Section 04 (Kanban board cards)

---

### Section 06: Projects List, Global Inbox & Settings Pages
**Goal:** Implement three full-page views: a Projects list page showing all registered projects, a Global Inbox page aggregating open questions across projects, and a Settings page with global settings, per-project settings, and phase-to-status mapping configuration.

**FRs:** FR-03.22, FR-03.23, FR-03.23a, FR-03.23b, FR-03.24, FR-03.25, FR-03.26

**Files:**
- `client/src/components/projects/ProjectsPage.tsx` — project list with status, activity, navigation
- `client/src/components/projects/ProjectCard.tsx` — individual project row/card
- `client/src/components/inbox/InboxPage.tsx` — global inbox view grouped by project
- `client/src/components/inbox/InboxItem.tsx` — single question with options and freetext
- `client/src/components/settings/SettingsPage.tsx` — settings shell with sections/tabs
- `client/src/components/settings/GlobalSettings.tsx` — port, concurrency, default autonomy
- `client/src/components/settings/ProjectSettings.tsx` — per-project profile, autonomy, env vars
- `client/src/components/settings/PhaseMapping.tsx` — phase-to-column mapping editor
- `client/src/hooks/useSettings.ts` — TanStack Query hooks for GET/PUT /api/settings
- `client/src/hooks/useInbox.ts` — TanStack Query hooks for GET /api/inbox, POST /api/inbox/:id/answer

**Depends on:** Split 02 Section 02 (layout/routing), Split 02 Section 03 (data hooks pattern)

---

### Section 07: Intent Detection Hint (Task Detail Chat)
**Goal:** Add a non-blocking intent detection hint inside the Task Detail chat input area. When a typed message is classified as a code change with confidence >= 0.7, a subtle hint appears below the input. Implements guard rules to skip classification for slash commands, questions, greetings, and short messages.

**FRs:** FR-03.20, FR-03.21

**Files:**
- `client/src/components/chat/IntentHint.tsx` — hint display with intent label, confidence, dismiss
- `client/src/hooks/useIntentDetection.ts` — debounced classification hook with guard logic
- `client/src/utils/intentGuards.ts` — guard functions (slash commands, questions, greetings, length)

**Depends on:** Split 02 Section 08 (chat engine with input area)
