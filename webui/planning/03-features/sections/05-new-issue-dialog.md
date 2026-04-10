# Section 05: New Issue Dialog — Enrichment Animation & Classify Integration

## Goal

Extend the New Issue Dialog (basic modal with Title + Description from Split 02 Section 05) with background auto-classification that runs after issue creation, and a card enrichment animation that visually updates the Kanban card when classification results (intent, complexity, risk flags, affected FRs) arrive. Also implement the "Start Task" action that spawns a Claude CLI process with the detected task type.

**Design reference:** `screens/12-new-issue.html`

## FRs Covered

- **FR-03.18** — The system SHALL provide a New Issue Dialog with Title and Description fields; on submit, the card appears immediately in the Backlog column.
- **FR-03.18a** — The system SHALL run auto-classification as a background process via POST /api/projects/:id/classify after issue creation, and enrich the card with results when available.
- **FR-03.19** — The system SHALL spawn a Claude CLI process with `/shipwright-iterate --type {detected_type}` when the user moves an issue to In Progress or triggers "Start Task".

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/hooks/useClassifyTask.ts` | TanStack Query mutation for background classification |
| `client/src/hooks/useStartTask.ts` | Mutation to trigger Claude CLI spawn with detected type |
| `client/src/components/board/CardEnrichment.tsx` | Badge appearance animation on Kanban card |
| `client/src/components/board/StartTaskButton.tsx` | "Start Task" button for card context menu / detail |
| `client/src/components/board/CardEnrichment.test.tsx` | Tests for enrichment animation |
| `client/src/components/board/StartTaskButton.test.tsx` | Tests for Start Task action |
| `client/src/hooks/useClassifyTask.test.ts` | Tests for classify mutation |

## Files to Modify

| File | Change |
|------|--------|
| `client/src/components/board/NewIssueModal.tsx` (from Split 02) | Add onSuccess callback that triggers background classification |
| `client/src/components/board/TaskCard.tsx` (from Split 02) | Integrate CardEnrichment for animated badge updates |

## Implementation Steps

1. **Create `useClassifyTask` hook** in `client/src/hooks/useClassifyTask.ts`:
   - Uses `useMutation` to POST to `/api/projects/${projectId}/classify`
   - Body: `{ taskId: string, title: string, description: string }`
   - On success: invalidates `['tasks', projectId]` query so the card re-renders with enrichment data
   - Fire-and-forget pattern: the mutation is triggered but the UI does not block on it
   - If the mutation fails, the card remains usable without enrichment (FR-03.18a graceful degradation)
   - Returns `{ classifyTask, isClassifying }`

2. **Create `CardEnrichment` component** in `client/src/components/board/CardEnrichment.tsx`:
   - Accepts `task` object with optional classification fields: `intent`, `complexity`, `riskFlags`, `affectedFrs`
   - If no classification data, renders nothing
   - When classification data appears (fields transition from undefined to defined), animate badges in:
     - Use CSS `@keyframes fadeInUp` animation: opacity 0->1, translateY 4px->0, duration 300ms
     - Stagger: each badge animates with a 100ms delay after the previous
   - Badge rendering:
     - **Intent**: `bug` (red), `feature` (blue), `change` (amber) — small pill badge
     - **Complexity**: `small` (green), `medium` (amber), `large` (red) — small pill badge
     - **Risk flags**: count displayed as `"N risks"` with warning icon if > 0
     - **Affected FRs**: comma-separated FR IDs as small muted text
   - Wrap in `<div className="flex flex-wrap gap-1 mt-1">`

3. **Modify `NewIssueModal` (from Split 02 Section 05):**
   - After successful issue creation (the `onSuccess` of the create task mutation):
     1. Close the modal (existing behavior)
     2. Call `classifyTask({ taskId: newTask.id, title, description })` to fire background classification
   - The modal submit flow remains fast — classification runs asynchronously after the modal closes
   - No loading indicator for classification in the modal itself

4. **Modify `TaskCard` (from Split 02 Section 04):**
   - Add `<CardEnrichment task={task} />` below the existing card content
   - The enrichment badges appear with animation when SSE pushes updated task data after classification completes
   - TanStack Query invalidation (from step 1) causes re-render with new data

5. **Create `useStartTask` hook** in `client/src/hooks/useStartTask.ts`:
   - Uses `useMutation` to POST to `/api/projects/${projectId}/tasks/${taskId}/start`
   - Body: `{ type: string }` (the detected intent type, e.g., `'bug'`, `'feature'`, `'change'`)
   - The backend spawns `claude --plugin-dir ... -p "/shipwright-iterate --type ${type}"` (FR-03.19)
   - On success: invalidates `['tasks', projectId]` to update card status to "running"
   - Returns `{ startTask, isStarting }`

6. **Create `StartTaskButton` component** in `client/src/components/board/StartTaskButton.tsx`:
   - Accepts `task` object and `projectId`
   - Renders a button: "Start Task" with a play icon
   - On click:
     - If `task.intent` exists (classification completed): call `startTask({ type: task.intent })`
     - If `task.intent` is undefined (classification pending/failed): show a small dropdown/dialog asking user to select type: "bug", "feature", "change" (FR-03.19 fallback)
   - Loading state: button shows spinner while starting
   - Disabled if task is already running
   - Placement: inside TaskCard context menu and/or Task Detail header

## Test Strategy

### Unit Tests

**`client/src/hooks/useClassifyTask.test.ts`** (renderHook + MSW):
- Mutation sends correct payload to classify endpoint
- On success, invalidates tasks query
- On failure, does not throw (fire-and-forget)

### Component Tests

**`client/src/components/board/CardEnrichment.test.tsx`**:
- Renders nothing when no classification data
- Renders intent badge when intent is present
- Renders complexity badge with correct color
- Renders risk flag count when riskFlags > 0
- Renders affected FR IDs
- Badges have animation classes applied

**`client/src/components/board/StartTaskButton.test.tsx`**:
- Clicking button with classified task calls startTask with correct type
- Clicking button without classification shows type selection dropdown
- Button disabled when task is already running
- Loading spinner shown while starting

## Dependencies

- **Split 02 Section 05** — `NewIssueModal` component to extend with classify callback
- **Split 02 Section 04** — `TaskCard` component to integrate enrichment badges
- **Split 01 Section 10** — POST /api/projects/:id/classify, POST /api/projects/:id/tasks/:id/start

## Acceptance Criteria

**FR-03.18: New Issue Dialog**
- [ ] Dialog shows Title and Description fields
- [ ] On submit, card appears immediately in Backlog
- [ ] Dialog closes after creation

**FR-03.18a: Background Auto-Classification**
- [ ] Classification runs in background after issue creation
- [ ] Intent, complexity, risk flags, and affected FRs written to card
- [ ] Card visually updates with badges without user interaction
- [ ] If classification fails, card remains usable

**FR-03.19: Start Task Action**
- [ ] "Start Task" spawns Claude CLI with detected type
- [ ] Card status updates to "running" immediately
- [ ] If no classification result, user is prompted for task type
