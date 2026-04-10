# Section 03: TanStack Query Data Hooks & SSE Integration

## Goal

Create all TanStack React Query hooks for consuming the backend REST APIs and a central SSE hook that listens to the server's event stream and triggers query cache invalidation. This section is the data backbone — every UI component in subsequent sections consumes data through these hooks rather than making raw fetch calls. SSE events flow through `queryClient.invalidateQueries()` to keep the UI in sync without direct state mutation (KD-02.06).

## FRs Covered

No FRs directly — this section supports all data-consuming FRs across the entire split by providing the data layer.

## Constraints Addressed

- **CO-02.02** — TanStack React Query for ALL server data; SSE triggers cache invalidation
- **CO-02.03** — Native EventSource API for SSE
- **CO-02.08** — All data from Split 01 REST APIs

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/lib/api.ts` | Shared fetch wrapper: base URL, error handling, typed responses |
| `client/src/lib/queryKeys.ts` | Centralized query key factory for cache management |
| `client/src/hooks/useProjects.ts` | Query hook: GET /api/projects |
| `client/src/hooks/useTasks.ts` | Query hook: GET /api/projects/:id/tasks |
| `client/src/hooks/useTask.ts` | Query hook: GET /api/projects/:id/tasks/:taskId (single task) |
| `client/src/hooks/useInbox.ts` | Query hook: GET /api/inbox |
| `client/src/hooks/useChat.ts` | Query hook: GET /api/projects/:id/chat/:taskId + send mutation |
| `client/src/hooks/usePipeline.ts` | Query hook: GET /api/projects/:id/pipeline |
| `client/src/hooks/useSSE.ts` | SSE EventSource hook with query invalidation |
| `client/src/hooks/useLocalStorage.ts` | Generic localStorage read/write hook |
| `client/src/lib/api.test.ts` | Tests for fetch wrapper |
| `client/src/hooks/useProjects.test.ts` | Tests for projects hook |
| `client/src/hooks/useTasks.test.ts` | Tests for tasks hook |
| `client/src/hooks/useSSE.test.ts` | Tests for SSE hook |
| `client/src/hooks/useLocalStorage.test.ts` | Tests for localStorage hook |
| `client/src/test/mocks/handlers.ts` | Updated: MSW handlers for all API endpoints |

## Implementation Steps

1. **Create `client/src/lib/api.ts`**:
   - Export `API_BASE` constant: `"/api"` (Vite proxy handles forwarding)
   - Export async `apiFetch<T>(path: string, options?: RequestInit): Promise<T>` that:
     - Prepends `API_BASE` to path
     - Sets `Content-Type: application/json` for non-GET requests
     - Calls `fetch()`, checks `response.ok`
     - On success: parses JSON, returns `data` field from `ApiResponse<T>` wrapper
     - On error: parses error body, throws typed `ApiError` with `error` and `detail` fields
   - Export `apiPost<T>(path: string, body: unknown): Promise<T>` convenience wrapper
   - Export `apiPatch<T>(path: string, body: unknown): Promise<T>` convenience wrapper

2. **Create `client/src/lib/queryKeys.ts`**:
   - Export a `queryKeys` object using the factory pattern:
     ```typescript
     export const queryKeys = {
       projects: {
         all: ['projects'] as const,
         detail: (id: string) => ['projects', id] as const,
       },
       tasks: {
         byProject: (projectId: string) => ['tasks', projectId] as const,
         detail: (projectId: string, taskId: string) => ['tasks', projectId, taskId] as const,
         all: ['tasks'] as const,
       },
       inbox: {
         all: ['inbox'] as const,
         count: ['inbox', 'count'] as const,
       },
       chat: {
         byTask: (projectId: string, taskId: string) => ['chat', projectId, taskId] as const,
       },
       pipeline: {
         byProject: (projectId: string) => ['pipeline', projectId] as const,
       },
     } as const;
     ```

3. **Create `client/src/hooks/useProjects.ts`**:
   - Export `useProjects()` — `useQuery` with key `queryKeys.projects.all`, fetches `GET /api/projects`, returns `Project[]`
   - Export `useProject(id: string)` — `useQuery` with key `queryKeys.projects.detail(id)`, fetches `GET /api/projects/${id}`, returns `Project`

4. **Create `client/src/hooks/useTasks.ts`**:
   - Export `useTasks(projectId?: string)` — when `projectId` is provided, fetch `GET /api/projects/${projectId}/tasks`; when undefined (All tab), fetch from all projects by iterating useProjects or using a dedicated endpoint
   - Returns `Task[]`
   - `enabled: true` always (tasks are the primary data)
   - `staleTime: 10_000` (10s, SSE handles freshness)

5. **Create `client/src/hooks/useTask.ts`**:
   - Export `useTask(projectId: string, taskId: string)` — `useQuery` fetching single task
   - Used by Task Detail page

6. **Create `client/src/hooks/useInbox.ts`**:
   - Export `useInbox()` — `useQuery` with key `queryKeys.inbox.all`, fetches `GET /api/inbox`, returns `InboxItem[]`
   - Export `useInboxCount()` — derives pending count from `useInbox()` data: `data.filter(item => item.status === "pending").length`
   - Export `useAnswerInbox()` — `useMutation` for `POST /api/inbox/:id/answer`, invalidates inbox queries on success

7. **Create `client/src/hooks/useChat.ts`**:
   - Export `useChat(projectId: string, taskId: string)` — `useQuery` fetching `GET /api/projects/${projectId}/chat/${taskId}`, returns `ChatMessage[]`
   - Export `useSendChat()` — `useMutation` for `POST /api/projects/${projectId}/chat`, body `{ message: string, taskId: string, model?: string, mode?: string, effort?: string }`, invalidates chat queries on success

8. **Create `client/src/hooks/usePipeline.ts`**:
   - Export `usePipeline(projectId: string)` — `useQuery` fetching `GET /api/projects/${projectId}/pipeline`, returns `PipelineRun`

9. **Create `client/src/hooks/useSSE.ts`**:
   - Export `useSSE(projectId?: string)` custom hook:
     - Creates an `EventSource` connection to `/api/events` (or `/api/projects/${projectId}/events` if scoped)
     - Obtains `queryClient` via `useQueryClient()`
     - On message, parse the SSE event type and payload
     - Invalidation map (SSE event type -> query keys to invalidate):
       - `task:created` -> `queryKeys.tasks.byProject(payload.projectId)`, `queryKeys.tasks.all`
       - `task:updated` -> `queryKeys.tasks.byProject(payload.projectId)`, `queryKeys.tasks.detail(payload.projectId, payload.taskId)`
       - `inbox:new` -> `queryKeys.inbox.all`
       - `inbox:answered` -> `queryKeys.inbox.all`
       - `chat:message` -> `queryKeys.chat.byTask(payload.projectId, payload.taskId)`
       - `pipeline:updated` -> `queryKeys.pipeline.byProject(payload.projectId)`
       - `project:updated` -> `queryKeys.projects.all`
     - **Reconnection** (QR-02.07): EventSource natively reconnects. Add `onerror` handler that logs and tracks connection state.
     - **Cleanup**: Close EventSource on component unmount via `useEffect` cleanup
     - Track `isConnected` state (true on `onopen`, false on `onerror`)
     - Return `{ isConnected }` for UI indicators

10. **Create `client/src/hooks/useLocalStorage.ts`**:
    - Generic hook: `useLocalStorage<T>(key: string, defaultValue: T): [T, (value: T) => void]`
    - Read from `localStorage` on mount, parse JSON
    - Write to `localStorage` on setter call, stringify JSON
    - Handle parse errors gracefully (fallback to default)
    - Use `useState` internally, sync with localStorage on change

11. **Update `client/src/test/mocks/handlers.ts`** with MSW handlers for all endpoints:
    - `GET /api/projects` — returns mock `Project[]`
    - `GET /api/projects/:id/tasks` — returns mock `Task[]`
    - `GET /api/inbox` — returns mock `InboxItem[]`
    - `POST /api/inbox/:id/answer` — returns success
    - `GET /api/projects/:id/chat/:taskId` — returns mock `ChatMessage[]`
    - `POST /api/projects/:id/chat` — returns success
    - `GET /api/projects/:id/pipeline` — returns mock `PipelineRun`
    - Define mock data factories for each type (reusable across tests)

12. **Wire SSE into the app shell**: Update `MainLayout.tsx` to call `useSSE()` at the layout level so all pages benefit from real-time updates.

13. **Wire inbox count into sidebar**: Update `SidebarNav.tsx` to call `useInboxCount()` and pass the count to `<InboxBadge />`. This completes FR-02.03.

## Test Strategy

### Unit Tests

| Test File | What It Tests |
|-----------|---------------|
| `client/src/lib/api.test.ts` | `apiFetch` success/error paths, JSON parsing, error throwing |
| `client/src/hooks/useProjects.test.ts` | Projects hook fetches and returns data |
| `client/src/hooks/useTasks.test.ts` | Tasks hook fetches by project, handles empty state |
| `client/src/hooks/useSSE.test.ts` | SSE hook creates EventSource, invalidates queries on events |
| `client/src/hooks/useLocalStorage.test.ts` | Read/write localStorage, handle missing/corrupt data |

### Test Details

- **api.ts**: Use MSW to mock success (200 + `{ data: [...] }`) and error (400 + `{ error: "..." }`) responses. Assert `apiFetch` returns unwrapped data on success and throws `ApiError` on failure.
- **useProjects**: Use `renderHook` with `QueryClientProvider` wrapper. MSW returns mock projects. Assert `result.current.data` matches mock.
- **useTasks**: Similar to useProjects, test with and without `projectId` parameter.
- **useSSE**: Mock `EventSource` globally (class mock that exposes `onmessage`, `onerror`, `close`). Simulate events by calling `onmessage` with typed payloads. Assert `queryClient.invalidateQueries` was called with correct keys.
- **useLocalStorage**: Mock `localStorage` (jsdom provides it). Test initial read, write, and corrupt-data fallback.

## Dependencies

- **Section 01** — Vite project, TanStack React Query, TypeScript types
- **Section 02** — MainLayout (for wiring SSE and inbox count)

## Acceptance Criteria

- [ ] All hooks fetch data from correct API endpoints
- [ ] `useSSE` creates EventSource connection and invalidates correct query keys per event type
- [ ] `useSSE` reconnects automatically after connection loss (EventSource native behavior)
- [ ] `useInboxCount` returns correct pending count derived from inbox data
- [ ] `useLocalStorage` persists and reads values correctly
- [ ] MSW handlers mock all API endpoints used by hooks
- [ ] All hook tests pass with `renderHook`
- [ ] Sidebar inbox badge updates in real-time via SSE -> useInboxCount chain (FR-02.03)
- [ ] No raw `fetch()` calls outside of `lib/api.ts`
