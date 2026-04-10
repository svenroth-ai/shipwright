# Section 01: Smart Viewer — Tab Management, Router & Markdown Renderer

## Goal

Build the Smart Viewer shell inside the Task Detail right panel with a scrollable tab bar for managing open files, a content-type router that selects the appropriate renderer based on file path and extension, and the Markdown renderer using react-markdown with remark-gfm and Mermaid diagram support. This section establishes the viewer architecture that all subsequent renderers (Section 02) plug into.

## FRs Covered

- **FR-03.01** — The system SHALL display multiple open files as tabs in the Smart Viewer, allowing the user to open, close, and switch between tabs.
- **FR-03.02** — The system SHALL render Markdown files using remark-gfm with Mermaid diagram support.
- **FR-03.05** — The system SHALL render JSON files as a collapsible tree view (stub renderer registered here; full implementation in Section 02).
- **FR-03.09** — The system SHALL render Mermaid diagrams inline for files under `compliance/`.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/types/viewer.ts` | ViewerTab, FileType enum, RendererProps interface |
| `client/src/hooks/useViewerTabs.ts` | Tab state management: open, close, activate, deduplicate |
| `client/src/hooks/useFileContent.ts` | TanStack Query hook for GET /api/projects/:id/docs?path=... |
| `client/src/components/viewer/SmartViewer.tsx` | Top-level viewer: tab bar + active renderer area |
| `client/src/components/viewer/ViewerTabBar.tsx` | Scrollable tab strip with close buttons per tab |
| `client/src/components/viewer/ViewerRouter.tsx` | Maps file path/extension to correct renderer component |
| `client/src/components/viewer/renderers/MarkdownRenderer.tsx` | react-markdown + remark-gfm + rehype-highlight |
| `client/src/components/viewer/renderers/MermaidBlock.tsx` | Lazy-loaded Mermaid diagram rendering for code blocks |
| `client/src/components/viewer/SmartViewer.test.tsx` | Tests for tab management and viewer shell |
| `client/src/components/viewer/ViewerRouter.test.tsx` | Tests for file type routing |
| `client/src/components/viewer/renderers/MarkdownRenderer.test.tsx` | Tests for Markdown rendering |
| `client/src/hooks/useViewerTabs.test.ts` | Tests for tab state hook |

## Design Reference

- **Primary:** `designs/screens/11-task-detail.html` — Right panel (Viewer ~40%), tab bar, content area, tab management (open/close/switch)

## Implementation Steps

1. **Define viewer types** in `client/src/types/viewer.ts`:
   - `FileType` union: `'markdown' | 'html' | 'code' | 'json' | 'spec' | 'plan' | 'consistency' | 'compliance' | 'url' | 'unknown'`
   - `ViewerTab` interface: `{ id: string; label: string; filePath: string; fileType: FileType; projectId: string }`
   - `RendererProps` interface: `{ tab: ViewerTab; content: string; projectId: string }`
   - `resolveFileType(filePath: string): FileType` — pure function that maps file path + extension to FileType. Rules:
     - `*.md` under `compliance/` -> `'compliance'`
     - `spec.md` -> `'spec'`
     - `plan.md` -> `'plan'`
     - `*.md` -> `'markdown'`
     - `*.html` under `designs/` -> `'html'`
     - `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.css`, `*.py` -> `'code'`
     - `*.json` containing `consistency_report` -> `'consistency'`
     - `*.json` -> `'json'`
     - `http://` or `https://` prefix -> `'url'`
     - fallback -> `'unknown'`

2. **Create `useViewerTabs` hook** in `client/src/hooks/useViewerTabs.ts`:
   - State: `tabs: ViewerTab[]`, `activeTabId: string | null`
   - `openTab(filePath: string, projectId: string)`: resolves FileType, generates id from filePath, checks for existing tab with same filePath — if found, activates it (no duplicate); otherwise creates new tab, appends to list, activates it
   - `closeTab(tabId: string)`: removes tab from list; if closed tab was active, activate the nearest remaining tab (prefer right neighbor, then left, then null)
   - `activateTab(tabId: string)`: sets activeTabId
   - `openUrl(url: string, label: string, projectId: string)`: creates a tab with fileType `'url'` and the URL as filePath
   - Return: `{ tabs, activeTab, openTab, closeTab, activateTab, openUrl }`

3. **Create `useFileContent` hook** in `client/src/hooks/useFileContent.ts`:
   - Uses `useQuery` with key `['file-content', projectId, filePath]`
   - Fetches `GET /api/projects/${projectId}/docs?path=${encodeURIComponent(filePath)}`
   - Returns `{ data: string, isLoading, error }`
   - Enabled only when filePath is truthy and fileType is not `'url'` (URLs don't need content fetch)
   - `staleTime: 30_000` (files don't change rapidly during viewing)

4. **Create `ViewerTabBar` component** in `client/src/components/viewer/ViewerTabBar.tsx`:
   - Renders a horizontally scrollable `<div role="tablist">` containing one button per tab
   - Each tab button: `<button role="tab" aria-selected={isActive}>` with file label text and a close button (`x` icon)
   - Active tab has `aria-selected="true"` and visual highlight (border-bottom in primary color)
   - Close button: `<button aria-label="Close ${tab.label}" onClick={closeTab}>` — stops propagation so clicking close doesn't also activate
   - Overflow: `overflow-x-auto` with `scrollbar-hide` utility for clean horizontal scroll

5. **Create `ViewerRouter` component** in `client/src/components/viewer/ViewerRouter.tsx`:
   - Accepts `tab: ViewerTab` and `projectId: string`
   - Switch on `tab.fileType`:
     - `'markdown'`, `'compliance'` -> `<MarkdownRenderer>`
     - `'code'` -> placeholder `<div>Code renderer (Section 02)</div>`
     - `'html'` -> placeholder
     - `'json'` -> placeholder
     - `'spec'` -> placeholder
     - `'plan'` -> placeholder
     - `'consistency'` -> placeholder
     - `'url'` -> placeholder
     - `'unknown'` -> `<div>Unsupported file type</div>`
   - Fetches content via `useFileContent` (skipped for `'url'` type) and passes to renderer

6. **Create `SmartViewer` component** in `client/src/components/viewer/SmartViewer.tsx`:
   - Accepts `projectId: string` from Task Detail context
   - Uses `useViewerTabs` hook
   - Renders `<ViewerTabBar>` at top if tabs are non-empty
   - Renders `<ViewerRouter>` for the active tab below the tab bar
   - If no tabs open, renders an empty state: "Open a file from the explorer or click a file link"
   - Exposes `openTab` and `openUrl` via React context (`ViewerContext`) so other components (File Explorer, chat links) can open files

7. **Create `MermaidBlock` component** in `client/src/components/viewer/renderers/MermaidBlock.tsx`:
   - Lazy-loads `mermaid` library via dynamic import on first render
   - Accepts `code: string` (the Mermaid source)
   - On mount/code change: calls `mermaid.render()` with a unique id, sets innerHTML to the SVG output
   - Error handling: if Mermaid parse fails, render the raw code in a `<pre>` block with an error note
   - Performance: renders within 2s for diagrams up to 50 nodes (QR-03.02)

8. **Create `MarkdownRenderer` component** in `client/src/components/viewer/renderers/MarkdownRenderer.tsx`:
   - Uses `react-markdown` with plugins: `remarkGfm`, `rehypeHighlight`
   - Custom component override for `code` blocks: if language is `mermaid`, render `<MermaidBlock>` instead of a code block
   - Wraps content in a `<div className="prose">` container for typographic styling
   - Handles compliance files (fileType `'compliance'`) identically — Mermaid blocks render as diagrams, rest as standard Markdown (FR-03.09)
   - Performance: first paint under 500ms for files up to 5000 lines (QR-03.01) — use `React.memo` to avoid unnecessary re-renders

## Test Strategy

### Unit Tests

**`client/src/types/viewer.ts` (tested inline or via `viewer.test.ts`)**:
- `resolveFileType('planning/spec.md')` returns `'spec'`
- `resolveFileType('planning/plan.md')` returns `'plan'`
- `resolveFileType('compliance/traceability.md')` returns `'compliance'`
- `resolveFileType('src/App.tsx')` returns `'code'`
- `resolveFileType('designs/mockup.html')` returns `'html'`
- `resolveFileType('data.json')` returns `'json'`
- `resolveFileType('report_consistency_report.json')` returns `'consistency'`
- `resolveFileType('https://localhost:3000')` returns `'url'`
- `resolveFileType('unknown.xyz')` returns `'unknown'`

**`client/src/hooks/useViewerTabs.test.ts`** (using `renderHook`):
- `openTab` adds a new tab and activates it
- `openTab` with same filePath activates existing tab instead of duplicating
- `closeTab` removes tab and activates nearest neighbor
- `closeTab` on last remaining tab sets activeTabId to null
- `activateTab` switches activeTabId
- `openUrl` creates a tab with fileType `'url'`

### Component Tests

**`client/src/components/viewer/SmartViewer.test.tsx`**:
- Renders empty state when no tabs are open
- Renders tab bar and active renderer when tabs exist
- Provides ViewerContext with openTab/openUrl functions

**`client/src/components/viewer/ViewerRouter.test.tsx`**:
- Routes `.md` file to MarkdownRenderer
- Routes `compliance/*.md` to MarkdownRenderer
- Routes unknown file type to fallback message

**`client/src/components/viewer/renderers/MarkdownRenderer.test.tsx`**:
- Renders GFM tables correctly
- Renders task lists with checkboxes
- Renders Mermaid code blocks as MermaidBlock component
- Renders links as clickable elements

## Dependencies

- **Split 02 Section 07** — Task Detail layout provides the viewer slot where SmartViewer mounts
- **Split 01 Section 10** — GET /api/projects/:id/docs API for file content
- **npm packages** — `react-markdown`, `remark-gfm`, `rehype-highlight`, `mermaid`

## Acceptance Criteria

**FR-03.01: Tab Management**
- [ ] User can open a file and it appears as a new tab
- [ ] User can close individual tabs via close button
- [ ] User can switch between open tabs by clicking
- [ ] Opening an already-open file activates its existing tab (no duplicate)

**FR-03.02: Markdown Rendering**
- [ ] GFM tables, task lists, and strikethrough render correctly
- [ ] Mermaid code blocks render as SVG diagrams
- [ ] Links within Markdown are clickable

**FR-03.09: Compliance Mermaid**
- [ ] Files under compliance/ with Mermaid code blocks render diagrams inline
- [ ] Non-Mermaid content in compliance files renders as standard Markdown
