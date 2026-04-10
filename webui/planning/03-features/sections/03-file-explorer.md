# Section 03: File Explorer — Directory Tree, Git Status & Click-to-Open

## Goal

Build a slide-in File Explorer panel inside the Task Detail view with a recursive directory tree supporting expand/collapse, git status indicators (M/A/D) per file, filtering to only relevant project directories, and click-to-open integration that opens files in the Smart Viewer tabs.

## FRs Covered

- **FR-03.11** — The system SHALL provide a slide-in File Explorer inside the Task Detail view with a recursive directory tree supporting expand/collapse.
- **FR-03.12** — The system SHALL display git status indicators (M/A/D) per file in the File Explorer.
- **FR-03.13** — The system SHALL filter the File Explorer to show only relevant directories: `src/`, `planning/`, `designs/`, `agent_docs/`, `compliance/`.
- **FR-03.14** — The system SHALL open a file in the Smart Viewer when the user clicks it in the File Explorer.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/types/explorer.ts` | FileTreeNode, GitStatus type definitions |
| `client/src/hooks/useFileTree.ts` | TanStack Query hook for GET /api/projects/:id/docs (tree mode) |
| `client/src/components/explorer/FileExplorer.tsx` | Slide-in panel shell with toggle button |
| `client/src/components/explorer/DirectoryTree.tsx` | Recursive tree container |
| `client/src/components/explorer/TreeNode.tsx` | Single file or directory node |
| `client/src/components/explorer/GitStatusBadge.tsx` | M/A/D indicator component |
| `client/src/components/explorer/FileExplorer.test.tsx` | Tests for explorer panel |
| `client/src/components/explorer/DirectoryTree.test.tsx` | Tests for tree rendering |
| `client/src/components/explorer/TreeNode.test.tsx` | Tests for node interaction |
| `client/src/components/explorer/GitStatusBadge.test.tsx` | Tests for git status display |

## Design Reference

- **Primary:** `designs/screens/11-task-detail.html` — File Explorer slide-in panel (inside Task Detail right side), tree structure, toggle button

## Implementation Steps

1. **Define explorer types** in `client/src/types/explorer.ts`:
   - `GitStatus` union: `'M' | 'A' | 'D' | null` (Modified, Added, Deleted, or clean)
   - `FileTreeNode` interface:
     ```typescript
     interface FileTreeNode {
       name: string;
       path: string;
       type: 'file' | 'directory';
       children?: FileTreeNode[];
       gitStatus?: GitStatus;
     }
     ```
   - `ALLOWED_DIRECTORIES` constant: `['src', 'planning', 'designs', 'agent_docs', 'compliance']` (FR-03.13)

2. **Create `useFileTree` hook** in `client/src/hooks/useFileTree.ts`:
   - Uses `useQuery` with key `['file-tree', projectId]`
   - Fetches `GET /api/projects/${projectId}/docs` (returns full tree with git status)
   - Post-processes response to filter root-level children to only `ALLOWED_DIRECTORIES` entries
   - `staleTime: 60_000` (tree structure changes infrequently)
   - Returns `{ tree: FileTreeNode[], isLoading, error, refetch }`

3. **Create `GitStatusBadge` component** in `client/src/components/explorer/GitStatusBadge.tsx`:
   - Accepts `status: GitStatus`
   - If `null`, renders nothing
   - `'M'`: renders `<span class="text-amber-500 text-xs font-mono">M</span>` (Modified — amber, VSCode convention)
   - `'A'`: renders `<span class="text-green-600 text-xs font-mono">A</span>` (Added — green)
   - `'D'`: renders `<span class="text-red-500 text-xs font-mono">D</span>` (Deleted — red)
   - Includes `aria-label` for accessibility: e.g., `aria-label="Modified"`

4. **Create `TreeNode` component** in `client/src/components/explorer/TreeNode.tsx`:
   - Accepts `node: FileTreeNode`, `depth: number`, `onFileClick: (path: string) => void`
   - **Directory node**: uses Radix `Collapsible` for expand/collapse
     - Trigger: chevron icon (right when collapsed, down when expanded) + folder icon + directory name
     - Content: recursively renders child `TreeNode` components
     - Indent: `padding-left: ${(depth + 1) * 16}px`
     - All directories start collapsed
   - **File node**: renders as a button with file-type icon + file name + `GitStatusBadge`
     - `onClick` calls `onFileClick(node.path)`
     - File icons: use simple SVG or emoji-based icons (document icon for generic, code icon for `.ts`/`.tsx`, markdown icon for `.md`)
     - Indent matches directory children level
   - Keyboard: Enter/Space on directory toggles collapse; Enter/Space on file opens it

5. **Create `DirectoryTree` component** in `client/src/components/explorer/DirectoryTree.tsx`:
   - Accepts `nodes: FileTreeNode[]`, `onFileClick: (path: string) => void`
   - Renders a `<div role="tree" aria-label="File explorer">` containing `TreeNode` for each root node
   - Each `TreeNode` gets `role="treeitem"` (directories also get `aria-expanded`)
   - If nodes array is empty, renders "No files found" message

6. **Create `FileExplorer` component** in `client/src/components/explorer/FileExplorer.tsx`:
   - Accepts `projectId: string` from Task Detail context
   - State: `isOpen: boolean` (default: `false`, explorer hidden by default — FR-03.11)
   - Toggle button: icon button in the Task Detail toolbar area with `aria-label="Toggle file explorer"` and folder icon
   - When open: renders a slide-in panel (`transform: translateX`) with `DirectoryTree` inside
     - Panel width: `280px`, slides in from the left side of the viewer area
     - Transition: `transition-transform duration-200 ease-in-out`
   - Uses `useFileTree(projectId)` for data
   - Loading state: skeleton tree with 5 placeholder items
   - `onFileClick` handler: reads `ViewerContext` from Section 01 and calls `openTab(filePath, projectId)` to open the file in the Smart Viewer (FR-03.14)

## Test Strategy

### Unit Tests

**`client/src/components/explorer/GitStatusBadge.test.tsx`**:
- Renders "M" with amber color for modified status
- Renders "A" with green color for added status
- Renders "D" with red color for deleted status
- Renders nothing for null status
- Has correct aria-label for each status

### Component Tests

**`client/src/components/explorer/TreeNode.test.tsx`**:
- Directory node renders with chevron and folder icon
- Clicking directory toggles children visibility
- File node renders with file name and git status badge
- Clicking file node calls onFileClick with correct path
- Keyboard Enter on file triggers onFileClick

**`client/src/components/explorer/DirectoryTree.test.tsx`**:
- Renders tree structure with correct nesting
- Empty tree shows "No files found" message
- Has role="tree" for accessibility

**`client/src/components/explorer/FileExplorer.test.tsx`**:
- Explorer is hidden by default
- Toggle button opens the slide-in panel
- Toggle button closes the panel when already open
- Loading state shows skeleton placeholders
- Clicking a file calls openTab via ViewerContext

## Dependencies

- **Section 01** — `ViewerContext` with `openTab` function for click-to-open integration
- **Split 02 Section 07** — Task Detail layout provides the explorer slot
- **Split 01 Section 10** — GET /api/projects/:id/docs API returns file tree with git status

## Acceptance Criteria

**FR-03.11: File Explorer Tree**
- [ ] Explorer slides in inside the Task Detail view when toggled
- [ ] Directories display as expandable/collapsible nodes
- [ ] Files display as leaf nodes with appropriate icons
- [ ] Explorer is hidden by default

**FR-03.12: Git Status Indicators**
- [ ] Modified files show "M" indicator (amber)
- [ ] Added files show "A" indicator (green)
- [ ] Deleted files show "D" indicator (red)
- [ ] Clean files show no indicator

**FR-03.13: Directory Filtering**
- [ ] Only src/, planning/, designs/, agent_docs/, and compliance/ directories are shown
- [ ] Other directories (node_modules/, .git/) are excluded

**FR-03.14: Click-to-Open**
- [ ] Clicking a file opens it in the Smart Viewer
- [ ] Correct renderer is selected based on file path and extension
