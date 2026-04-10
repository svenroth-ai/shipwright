# Section 05: New Issue Modal & Background Auto-Classify

## Goal

Build the New Issue creation flow: a modal dialog with Title and Description fields, immediate card creation in the Backlog column upon submission (before classification), background auto-classification via `POST /api/projects/:id/classify`, and in-place card enrichment (intent badge, complexity, FR links) when classification results arrive via SSE. The user sees instant feedback — the card appears immediately and evolves as classification data arrives.

## FRs Covered

- **FR-02.13** — Modal dialog with Title (required) and Description (optional) fields.
- **FR-02.14** — Card appears immediately in Backlog upon submission, before classification.
- **FR-02.15** — Background auto-classification via POST /api/projects/:id/classify after creation.
- **FR-02.16** — Card auto-enrichment in-place when classification arrives (intent badge, complexity, FR links).

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/components/board/NewIssueModal.tsx` | Radix Dialog: title + description form |
| `client/src/hooks/useCreateTask.ts` | Mutation: create task + trigger classify |
| `client/src/components/board/IntentBadge.tsx` | Intent badge component (fix/feat/chg) |
| `client/src/components/board/ComplexityIndicator.tsx` | Complexity indicator (low/medium/high) |
| `client/src/components/board/NewIssueModal.test.tsx` | Tests for modal behavior |
| `client/src/hooks/useCreateTask.test.ts` | Tests for create + classify flow |
| `client/src/components/board/IntentBadge.test.tsx` | Tests for intent badge rendering |

## Design Reference

- **Primary:** `designs/screens/12-new-issue.html` — Modal dialog layout, title + description fields, submit button placement, loading state

## Implementation Steps

1. **Create `client/src/hooks/useCreateTask.ts`**:
   - Export `useCreateTask()` hook:
     - Uses `useMutation` for `POST /api/projects/:id/tasks` with body `{ description: string, title?: string }`
     - On success:
       1. Invalidate task queries (card appears in Backlog)
       2. Fire-and-forget `POST /api/projects/:id/classify` with the new task ID
     - The classify call is intentionally not awaited — classification happens in the background
     - If classify fails, the card stays in Backlog with title only (graceful degradation)
   - Return `{ createTask, isCreating }` from the hook

2. **Create `client/src/components/board/NewIssueModal.tsx`**:
   - Props: `open: boolean`, `onOpenChange: (open: boolean) => void`, `activeProjectId: string | null`, `projects: Project[]`
   - Use `@radix-ui/react-dialog` for accessible modal
   - Form fields:
     - Title: `<input>` (required), placeholder "What needs to be done?"
     - Description: `<textarea>` (optional), placeholder "Add details, context, or acceptance criteria..."
     - Project selector: when `activeProjectId` is null (All tab), show a `<select>` dropdown to choose project. When a project tab is active, pre-fill and hide the selector.
   - Submit button: disabled when Title is empty, styled as primary CTA
   - Cancel button: closes modal
   - Keyboard: Enter in title field focuses description; Ctrl+Enter submits; Escape closes
   - On submit:
     1. Call `createTask({ projectId, title, description })`
     2. Close modal immediately (optimistic — card appears via query invalidation)
     3. Clear form fields
   - Overlay: semi-transparent backdrop, click outside closes

3. **Create `client/src/components/board/IntentBadge.tsx`**:
   - Props: `intent?: string`
   - Return `null` when intent is undefined
   - Map: `fix` -> red pill "fix", `feat` -> green pill "feat", `chg` -> blue pill "chg"
   - Styling: similar to PhaseTag but smaller (8px text)

4. **Create `client/src/components/board/ComplexityIndicator.tsx`**:
   - Props: `complexity?: string`
   - Return `null` when undefined
   - Display as text label: "Low" (green), "Medium" (amber), "High" (red)
   - Small text (10px), muted colors

5. **Update `client/src/components/board/TaskCard.tsx`**:
   - Add intent badge rendering when `task.intent` is set
   - Add complexity indicator when `task.complexity` is set
   - Add loading shimmer effect when task has no intent AND was recently created (within last 30 seconds) — indicates pending classification
   - Animate enrichment: new elements fade in with CSS transition (`opacity 0 -> 1, 300ms ease`)

6. **Wire modal into `client/src/pages/KanbanPage.tsx`**:
   - Add `showNewIssue` state (boolean)
   - Pass `onClick={() => setShowNewIssue(true)}` to `<NewIssueButton />`
   - Render `<NewIssueModal open={showNewIssue} onOpenChange={setShowNewIssue} activeProjectId={activeProjectId} projects={projects} />`

## Test Strategy

### Unit Tests

| Test File | What It Tests |
|-----------|---------------|
| `client/src/components/board/NewIssueModal.test.tsx` | Modal opens/closes; form validation; submit flow |
| `client/src/hooks/useCreateTask.test.ts` | Mutation calls correct API; triggers classify; handles errors |
| `client/src/components/board/IntentBadge.test.tsx` | Renders correct pill per intent; hidden when undefined |

### Test Details

- **NewIssueModal**: Render with `open={true}`. Assert Title and Description fields visible. Type in Title, assert Submit button becomes enabled. Submit form, assert `createTask` mutation called with correct payload. Assert modal closes after submit. Test with `activeProjectId=null`, assert project selector appears.
- **useCreateTask**: Use `renderHook`. MSW handlers for POST `/api/projects/:id/tasks` (success) and POST `/api/projects/:id/classify` (success). Call `createTask`, assert both endpoints were hit. Test classify failure: MSW returns 500 for classify, assert task still created successfully.
- **IntentBadge**: Render with `intent="fix"`, assert red pill with text "fix". Render with `intent={undefined}`, assert nothing rendered.

## Dependencies

- **Section 03** — `useMutation`, `useQueryClient`, `queryKeys`, `apiPost`
- **Section 04** — `KanbanPage`, `NewIssueButton`, `TaskCard` (updated with enrichment)

## Acceptance Criteria

From spec:
- [ ] Modal opens centered with overlay backdrop
- [ ] Title field is required, Description is optional
- [ ] Modal closes on Escape, backdrop click, or Cancel button
- [ ] Submit button disabled when Title is empty
- [ ] If project tab selected, issue created for that project; if "All", project selector appears
- [ ] Card appears in Backlog within 500ms of submission
- [ ] Card initially shows title only (no classification data)
- [ ] Subtle loading indicator signals pending classification
- [ ] POST /api/projects/:id/classify called after task creation
- [ ] Classification runs asynchronously — modal already closed
- [ ] If classification fails, card remains in Backlog with title only
- [ ] Intent badge (fix/feat/chg) appears after classification
- [ ] Complexity indicator appears after classification
- [ ] Card update animated (fade-in of new elements)
