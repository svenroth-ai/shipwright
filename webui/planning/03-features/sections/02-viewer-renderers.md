# Section 02: Viewer Renderers — HTML, JSON, Overlays, Dashboard & URLs

## Goal

Implement the remaining content-type renderers that plug into the Smart Viewer router established in Section 01: syntax-highlighted code with line numbers, sandboxed HTML iframe preview for design mockups, collapsible JSON tree view, spec FR badge overlay, plan section progress overlay, consistency dashboard table, and external URL iframe tabs. After this section, the Smart Viewer supports all file types defined in the spec.

## FRs Covered

- **FR-03.04** — The system SHALL render TypeScript/TSX files with syntax highlighting via rehype-highlight.
- **FR-03.06** — The system SHALL render `spec.md` files with FR status badges (pass/fail/pending).
- **FR-03.07** — The system SHALL render `plan.md` files with a section progress overlay.
- **FR-03.08** — The system SHALL render `*_consistency_report.json` files as a consistency dashboard.
- **FR-03.10** — The system SHALL display external URLs as iframe tabs in the Smart Viewer.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/components/viewer/renderers/CodeRenderer.tsx` | Syntax highlighting + line numbers |
| `client/src/components/viewer/renderers/HtmlPreviewRenderer.tsx` | Sandboxed iframe for design HTML files |
| `client/src/components/viewer/renderers/JsonTreeRenderer.tsx` | Collapsible JSON tree view |
| `client/src/components/viewer/renderers/JsonTreeNode.tsx` | Single node in JSON tree (recursive) |
| `client/src/components/viewer/renderers/SpecOverlayRenderer.tsx` | Markdown + FR status badges |
| `client/src/components/viewer/renderers/PlanOverlayRenderer.tsx` | Markdown + section progress bars |
| `client/src/components/viewer/renderers/ConsistencyDashboard.tsx` | Table with pass/warn/fail per category |
| `client/src/components/viewer/renderers/ExternalUrlRenderer.tsx` | Iframe for localhost/external URLs |
| `client/src/components/viewer/renderers/CodeRenderer.test.tsx` | Tests for code renderer |
| `client/src/components/viewer/renderers/JsonTreeRenderer.test.tsx` | Tests for JSON tree |
| `client/src/components/viewer/renderers/SpecOverlayRenderer.test.tsx` | Tests for spec overlay |
| `client/src/components/viewer/renderers/ConsistencyDashboard.test.tsx` | Tests for consistency dashboard |
| `client/src/components/viewer/renderers/ExternalUrlRenderer.test.tsx` | Tests for URL iframe |

## Files to Modify

| File | Change |
|------|--------|
| `client/src/components/viewer/ViewerRouter.tsx` | Replace placeholder renderers with real components |

## Implementation Steps

1. **Create `CodeRenderer`** in `client/src/components/viewer/renderers/CodeRenderer.tsx`:
   - Accepts `content: string` and infers language from `tab.filePath` extension (`.ts` -> `typescript`, `.tsx` -> `tsx`, `.py` -> `python`, etc.)
   - Uses `rehype-highlight` for syntax highlighting by rendering content through `react-markdown` with a single code fence wrapper: ````${language}\n${content}\n````
   - Adds line numbers via a CSS counter on `<pre>` lines: split content by `\n`, wrap each line in a `<span>` with `data-line-number`
   - Alternatively: use a custom `<code>` component that splits into numbered lines post-highlight
   - TailwindCSS: monospace font, `overflow-x-auto`, `text-sm`

2. **Create `HtmlPreviewRenderer`** in `client/src/components/viewer/renderers/HtmlPreviewRenderer.tsx`:
   - Renders a `<iframe sandbox="allow-scripts allow-same-origin" srcDoc={content}>` (QR-03.04: sandboxed to prevent injection)
   - Iframe fills available viewer space: `width: 100%`, `height: 100%`, `border: none`
   - Only renders for files matching `designs/*.html` (enforced by ViewerRouter type routing)
   - Adds a small toolbar above the iframe with the file name and a "Refresh" button that re-sets srcDoc

3. **Create `JsonTreeRenderer`** and `JsonTreeNode`**:
   - `JsonTreeRenderer`: parses `content` as JSON. If parse fails, renders error message with the raw text. If valid, passes root object to `JsonTreeNode`.
   - `JsonTreeNode`: recursive component accepting `name: string`, `value: unknown`, `depth: number`, `defaultExpanded: boolean`
     - Objects/arrays: render as collapsible nodes using Radix `Collapsible`. Show key count (`{3 keys}`) or array length (`[5 items]`) when collapsed.
     - Primitives: render inline with type-based coloring (strings: green, numbers: blue, booleans: purple, null: gray)
     - Root level expanded by default, all nested levels collapsed by default (FR-03.05)
   - Indent: `padding-left: ${depth * 16}px`
   - Keyboard navigation: Enter/Space toggles expand/collapse (via Radix Collapsible)

4. **Create `SpecOverlayRenderer`**:
   - Renders `spec.md` content as Markdown (reuses `MarkdownRenderer` internally)
   - Parses FR table rows from the Markdown content using regex: `| FR-XX.XX |`
   - For each FR found, fetches status from event data via a `useSpecFrStatus(projectId)` hook (TanStack Query on pipeline/events endpoint)
   - Injects inline badges after each FR ID: `<span class="badge badge-pass">PASS</span>`, `badge-fail`, or `badge-pending`
   - Badge colors: pass = green, fail = red, pending = amber (TailwindCSS)

5. **Create `PlanOverlayRenderer`**:
   - Renders `plan.md` content as Markdown (reuses `MarkdownRenderer` internally)
   - Parses section headers from Markdown: `### Section XX: ...`
   - For each section, queries completion status via `useSectionProgress(projectId)` hook
   - Renders a small progress bar next to each section header: `<div class="h-2 bg-primary rounded" style="width: ${pct}%">`
   - Sections with 0% show as empty bar with "Not started" label; 100% shows checkmark

6. **Create `ConsistencyDashboard`**:
   - Parses JSON content (a consistency report with categories array)
   - Renders a `<table>` with columns: Category, Status, Details
   - Status cell uses color-coded badges: PASS (green), WARN (amber), FAIL (red)
   - If JSON is malformed, falls back to `JsonTreeRenderer`
   - Table is responsive: horizontal scroll on narrow viewports

7. **Create `ExternalUrlRenderer`**:
   - Renders a `<iframe src={tab.filePath} sandbox="allow-scripts allow-same-origin allow-popups">` for URLs
   - Fills available space: `width: 100%`, `height: 100%`
   - Toolbar above iframe: URL displayed as text + "Open in Browser" link (`<a target="_blank">`)
   - Loading state: shows spinner while iframe loads (listen to iframe `onLoad` event)

8. **Update `ViewerRouter`** to replace all placeholder `<div>` elements with the real renderer components. Add lazy loading via `React.lazy()` for heavier renderers (JsonTreeRenderer, ExternalUrlRenderer) to keep initial bundle small.

## Test Strategy

### Unit Tests

**`client/src/components/viewer/renderers/CodeRenderer.test.tsx`**:
- Renders TypeScript content with syntax highlighting classes applied
- Displays line numbers alongside code
- Handles empty content gracefully

**`client/src/components/viewer/renderers/JsonTreeRenderer.test.tsx`**:
- Renders valid JSON with root level expanded
- Nested objects are collapsed by default
- Clicking a collapsed node expands it
- Invalid JSON shows error message
- Primitive values display with type-appropriate styling

**`client/src/components/viewer/renderers/SpecOverlayRenderer.test.tsx`**:
- Renders spec Markdown content correctly
- FR IDs have status badges injected (pass/fail/pending)
- Missing FR status data shows pending badges

**`client/src/components/viewer/renderers/ConsistencyDashboard.test.tsx`**:
- Renders table with correct columns
- PASS/WARN/FAIL badges show correct colors
- Malformed JSON falls back to tree view

**`client/src/components/viewer/renderers/ExternalUrlRenderer.test.tsx`**:
- Renders iframe with correct src attribute
- Displays URL in toolbar
- "Open in Browser" link has correct href and target

## Dependencies

- **Section 01** — SmartViewer shell, ViewerRouter, ViewerTab types, useFileContent hook
- **Split 01 Section 10** — docs API, pipeline API (for FR status and section progress)
- **npm packages** — `react-markdown`, `remark-gfm`, `rehype-highlight` (already installed in Section 01)

## Acceptance Criteria

**FR-03.04: Syntax Highlighting**
- [ ] `.ts` and `.tsx` files display with language-appropriate syntax highlighting
- [ ] Line numbers are visible alongside the code

**FR-03.05: JSON Tree View**
- [ ] JSON files render as an interactive tree with collapsible nodes
- [ ] Root level expanded, nested levels collapsed by default
- [ ] Invalid JSON displays error message

**FR-03.06: Spec FR Badges**
- [ ] spec.md renders with pass/fail/pending badges next to FR IDs

**FR-03.07: Plan Progress Overlay**
- [ ] plan.md renders with progress bars next to section headers

**FR-03.08: Consistency Dashboard**
- [ ] Consistency report JSON renders as table with pass/warn/fail badges

**FR-03.10: External URL Tabs**
- [ ] External URLs render inside iframe tabs
- [ ] "Open in Browser" link works correctly
