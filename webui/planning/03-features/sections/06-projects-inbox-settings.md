# Section 06: Projects List, Global Inbox & Settings Pages

## Goal

Implement three full-page views that slot into the sidebar navigation: a Projects page listing all registered projects with status and navigation, a Global Inbox page aggregating open questions from all projects with answer delivery, and a Settings page with global settings, per-project settings, and phase-to-status mapping configuration.

## FRs Covered

- **FR-03.22** — The system SHALL provide a Global Inbox view aggregating all open questions across projects.
- **FR-03.23** — The system SHALL deliver inbox answers via POST /api/inbox/:id/answer.
- **FR-03.23a** — The system SHALL provide a Projects page listing all registered projects with name, status, last activity, and phase progress.
- **FR-03.23b** — The system SHALL allow navigating from Projects page to a project's Task Board or Settings.
- **FR-03.24** — The system SHALL provide a Settings page with global and per-project settings.
- **FR-03.25** — The system SHOULD populate env vars dynamically based on stack profile (shared with Section 04).
- **FR-03.26** — The system SHALL allow phase-to-status mapping configuration per project.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/components/projects/ProjectsPage.tsx` | Full-page project list view |
| `client/src/components/projects/ProjectCard.tsx` | Individual project row with status, activity, actions |
| `client/src/components/inbox/InboxPage.tsx` | Full-page global inbox view |
| `client/src/components/inbox/InboxItem.tsx` | Single question with option buttons and freetext |
| `client/src/components/inbox/InboxEmptyState.tsx` | Empty state when no open questions |
| `client/src/components/settings/SettingsPage.tsx` | Settings shell with tabbed/section layout |
| `client/src/components/settings/GlobalSettings.tsx` | Port, concurrency, default autonomy |
| `client/src/components/settings/ProjectSettings.tsx` | Per-project profile, autonomy, env vars |
| `client/src/components/settings/PhaseMapping.tsx` | Phase-to-column mapping editor |
| `client/src/hooks/useSettings.ts` | TanStack Query hooks for GET/PUT /api/settings |
| `client/src/hooks/useInbox.ts` | TanStack Query hooks for GET /api/inbox, POST answer |
| `client/src/types/settings.ts` | GlobalSettings, ProjectSettings, PhaseMapping interfaces |
| `client/src/types/inbox.ts` | InboxQuestion, InboxAnswer interfaces |
| `client/src/components/projects/ProjectsPage.test.tsx` | Tests for project list |
| `client/src/components/inbox/InboxPage.test.tsx` | Tests for inbox view |
| `client/src/components/settings/SettingsPage.test.tsx` | Tests for settings |
| `client/src/components/settings/PhaseMapping.test.tsx` | Tests for phase mapping |

## Files to Modify

| File | Change |
|------|--------|
| `client/src/App.tsx` | Add routes for /projects, /inbox, /settings |

## Implementation Steps

1. **Define settings types** in `client/src/types/settings.ts`:
   ```typescript
   interface GlobalSettings {
     port: number;
     maxConcurrent: number;
     defaultAutonomy: 'guided' | 'autonomous';
   }

   interface ProjectSettings {
     projectId: string;
     profileId: string;
     autonomy: 'guided' | 'autonomous';
     envVars: Record<string, string>;
     phaseMapping: PhaseMapping;
   }

   interface PhaseMapping {
     backlog: string[];      // e.g., ['project', 'design']
     inProgress: string[];   // e.g., ['plan', 'build']
     inReview: string[];     // e.g., ['test', 'compliance']
     done: string[];         // e.g., ['deploy', 'changelog']
   }

   const SHIPWRIGHT_PHASES = [
     'project', 'design', 'plan', 'build',
     'test', 'deploy', 'changelog', 'compliance'
   ] as const;

   const DEFAULT_PHASE_MAPPING: PhaseMapping = {
     backlog: ['project', 'design'],
     inProgress: ['plan', 'build'],
     inReview: ['test', 'compliance'],
     done: ['deploy', 'changelog'],
   };
   ```

2. **Define inbox types** in `client/src/types/inbox.ts`:
   ```typescript
   interface InboxQuestion {
     id: string;
     projectId: string;
     projectName: string;
     taskId: string;
     taskTitle: string;
     question: string;
     options?: string[];
     createdAt: string;
   }

   interface InboxAnswer {
     questionId: string;
     answer: string;
   }
   ```

3. **Create `useSettings` hook** in `client/src/hooks/useSettings.ts`:
   - `useGlobalSettings()`: `useQuery` with key `['settings', 'global']`, fetches GET /api/settings
   - `useUpdateGlobalSettings()`: `useMutation` for PUT /api/settings, invalidates `['settings', 'global']`
   - `useProjectSettings(projectId)`: `useQuery` with key `['settings', 'project', projectId]`, fetches GET /api/settings/projects/:id
   - `useUpdateProjectSettings(projectId)`: `useMutation` for PUT /api/settings/projects/:id
   - `useUpdatePhaseMapping(projectId)`: `useMutation` for PUT /api/settings/projects/:id/phase-mapping, invalidates `['tasks', projectId]` (cards may move columns)

4. **Create `useInbox` hook** in `client/src/hooks/useInbox.ts`:
   - `useInboxQuestions()`: `useQuery` with key `['inbox']`, fetches GET /api/inbox, `refetchInterval: 10_000` (poll for new questions; also updated via SSE)
   - `useAnswerQuestion()`: `useMutation` for POST /api/inbox/:id/answer, on success invalidates `['inbox']`

5. **Create `ProjectCard` component** in `client/src/components/projects/ProjectCard.tsx`:
   - Accepts `project` with fields: `id`, `name`, `status` (`active` | `paused`), `lastActivity: string`, `currentPhase: string`, `progress: number`
   - Renders as a horizontal card/row:
     - Left: project name (bold) + status badge (green for active, gray for paused)
     - Center: current phase label + small progress bar
     - Right: last activity as relative time ("2 hours ago") + action buttons
   - Action buttons:
     - "Open Board" -> navigates to `/projects/${id}` (the project's filtered board view)
     - "Settings" -> navigates to `/settings?project=${id}` (FR-03.23b)
   - Keyboard: entire card is focusable, Enter opens board

6. **Create `ProjectsPage` component** in `client/src/components/projects/ProjectsPage.tsx`:
   - Uses `useProjects()` hook (from Split 02) to get all projects
   - Renders page header: "Projects" + "New Project" button (opens Project Wizard from Section 04)
   - Renders list of `ProjectCard` components
   - Empty state: "No projects yet. Create your first project to get started." with a "Create Project" button
   - Loading state: 3 skeleton cards

7. **Create `InboxItem` component** in `client/src/components/inbox/InboxItem.tsx`:
   - Accepts `question: InboxQuestion` and `onAnswer: (questionId: string, answer: string) => void`
   - Renders:
     - Header: project name badge + task title (truncated)
     - Body: question text
     - Options: if `options` array exists, render a button per option. Clicking sends that option as the answer.
     - Freetext: text input + "Send" button below options. Allows typing a custom answer.
   - After answering: item fades out (CSS transition) and is removed from the list on next query invalidation

8. **Create `InboxEmptyState` component** in `client/src/components/inbox/InboxEmptyState.tsx`:
   - Renders a centered illustration/icon with text: "All caught up! No open questions."
   - Muted color, friendly tone

9. **Create `InboxPage` component** in `client/src/components/inbox/InboxPage.tsx`:
   - Uses `useInboxQuestions()` to fetch all open questions
   - Groups questions by `projectName` using a simple reduce
   - Renders project group headers (project name + question count)
   - Under each header, renders `InboxItem` components
   - If no questions, renders `InboxEmptyState`
   - Loading state: 3 skeleton items
   - `onAnswer` handler: calls `answerQuestion` mutation from `useAnswerQuestion()`

10. **Create `GlobalSettings` component** in `client/src/components/settings/GlobalSettings.tsx`:
    - Uses `useGlobalSettings()` for current values
    - Form fields:
      - **Port**: number input, default 3847
      - **Max Concurrent**: number input or range slider (1-10), default 3
      - **Default Autonomy**: Radix RadioGroup, "Guided" / "Autonomous"
    - "Save" button: calls `updateGlobalSettings` mutation
    - Success: brief toast/inline "Saved" confirmation
    - Changes take effect without server restart (FR-03.24)

11. **Create `ProjectSettings` component** in `client/src/components/settings/ProjectSettings.tsx`:
    - Accepts `projectId` (from dropdown or URL param)
    - Uses `useProjectSettings(projectId)` for current values
    - Form fields:
      - **Profile**: Radix Select dropdown with available profiles
      - **Autonomy**: Radix RadioGroup
      - **Environment Variables**: key-value editor (reuse pattern from EnvVarsStep in Section 04)
    - "Save" button: calls `updateProjectSettings` mutation

12. **Create `PhaseMapping` component** in `client/src/components/settings/PhaseMapping.tsx`:
    - Accepts `projectId`
    - Uses `useProjectSettings(projectId)` to read current mapping
    - Renders 4 columns (Backlog, In Progress, In Review, Done) as labeled drop zones
    - Each Shipwright phase is a draggable chip/pill. Alternatively (simpler): each phase has a Radix Select dropdown choosing which column it maps to.
    - Each phase can be assigned to exactly one column (FR-03.26)
    - Default mapping provided for new projects (`DEFAULT_PHASE_MAPPING`)
    - "Save" button: calls `updatePhaseMapping` mutation. On success, invalidates tasks query so cards reposition.
    - Visual: columns rendered side-by-side, phases as pills/tags within each column

13. **Create `SettingsPage` component** in `client/src/components/settings/SettingsPage.tsx`:
    - Uses Radix `Tabs` for section navigation: "Global", "Projects", "Phase Mapping"
    - **Global tab**: renders `<GlobalSettings />`
    - **Projects tab**: project selector dropdown at top, then `<ProjectSettings projectId={selected} />`
    - **Phase Mapping tab**: project selector dropdown at top, then `<PhaseMapping projectId={selected} />`
    - URL param `?project=` pre-selects the project in Projects/Phase Mapping tabs

14. **Add routes** to `client/src/App.tsx`:
    - `/projects` -> `<ProjectsPage />`
    - `/inbox` -> `<InboxPage />`
    - `/settings` -> `<SettingsPage />`

## Test Strategy

### Unit Tests

**`client/src/hooks/useSettings.test.ts`** (renderHook + MSW):
- `useGlobalSettings` fetches and returns settings
- `useUpdateGlobalSettings` sends PUT and invalidates query
- `useUpdatePhaseMapping` invalidates tasks query on success

**`client/src/hooks/useInbox.test.ts`** (renderHook + MSW):
- `useInboxQuestions` fetches and returns questions
- `useAnswerQuestion` sends POST and invalidates inbox query

### Component Tests

**`client/src/components/projects/ProjectsPage.test.tsx`**:
- Renders list of project cards
- Empty state shown when no projects
- "New Project" button is present
- Project card "Open Board" navigates correctly

**`client/src/components/inbox/InboxPage.test.tsx`**:
- Renders questions grouped by project
- Clicking option button sends answer
- Freetext submit sends answer
- Empty state shown when no questions
- Answered items removed from list

**`client/src/components/settings/SettingsPage.test.tsx`**:
- Tab navigation between Global, Projects, Phase Mapping
- Global settings form renders and saves
- Per-project settings load for selected project

**`client/src/components/settings/PhaseMapping.test.tsx`**:
- Renders 4 columns with phase assignments
- Changing a phase's column updates the mapping
- Default mapping applied for new projects
- Save triggers mutation and invalidates tasks

## Dependencies

- **Split 02 Section 02** — Layout and routing (sidebar navigation links to /projects, /inbox, /settings)
- **Split 02 Section 03** — Data hooks pattern (TanStack Query, useProjects)
- **Split 01 Section 10** — Settings API (GET/PUT /api/settings), Inbox API (GET /api/inbox, POST /api/inbox/:id/answer), Projects API

## Acceptance Criteria

**FR-03.22: Global Inbox View**
- [ ] All open questions from all projects displayed
- [ ] Items grouped by project
- [ ] Each item shows project name, task context, question text, and answer options

**FR-03.23: Inbox Answer Delivery**
- [ ] Clicking option button sends answer via POST
- [ ] Freetext answer submits correctly
- [ ] Answered items removed from view

**FR-03.23a: Projects Page**
- [ ] Lists all registered projects with name, status, last activity, phase progress
- [ ] Loading and empty states render correctly

**FR-03.23b: Project Navigation**
- [ ] "Open Board" navigates to project's board
- [ ] "Settings" navigates to project settings

**FR-03.24: Settings Page**
- [ ] Global settings (port, concurrency, autonomy) editable and persist
- [ ] Per-project settings editable and persist
- [ ] Changes take effect without server restart

**FR-03.26: Phase-to-Status Mapping**
- [ ] Per-project mapping of phases to Kanban columns
- [ ] Each phase assigned to exactly one column
- [ ] Default mapping provided for new projects
- [ ] Changes immediately update board column placement
