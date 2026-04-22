import { http, HttpResponse } from 'msw';
import type { HttpHandler } from 'msw';
import type { Project, Task, InboxItem, ChatMessage, PipelineRun } from '../../types';

export const mockProjects: Project[] = [
  {
    id: 'proj-1',
    name: 'Test Project',
    path: '/tmp/test-project',
    profile: 'custom',
    status: 'active',
    lastActive: '2026-04-10T10:00:00Z',
    createdAt: '2026-04-01T00:00:00Z',
  },
];

export const mockTasks: Task[] = [
  {
    id: 'task-1',
    projectId: 'proj-1',
    title: 'Implement auth',
    description: 'Implement auth',
    status: 'running',
    kanbanStatus: 'in_progress',
    currentPhase: 'build',
    sessionId: 'session-1',
    createdAt: '2026-04-10T10:00:00Z',
    updatedAt: '2026-04-10T10:05:00Z',
  },
  {
    id: 'task-2',
    projectId: 'proj-1',
    title: 'Fix login bug',
    description: 'Fix login bug',
    status: 'done',
    kanbanStatus: 'done',
    sessionId: 'session-2',
    createdAt: '2026-04-09T08:00:00Z',
    updatedAt: '2026-04-09T09:00:00Z',
  },
];

export const mockInboxItems: InboxItem[] = [
  {
    id: 'inbox-1',
    projectId: 'proj-1',
    taskId: 'task-1',
    parts: [
      {
        question: 'Which auth provider?',
        options: ['Supabase', 'Firebase'],
      },
    ],
    status: 'pending',
    createdAt: '2026-04-10T10:02:00Z',
  },
];

export const mockChatMessages: ChatMessage[] = [
  {
    id: 'msg-1',
    taskId: 'task-1',
    type: 'user',
    content: 'Start building auth',
    timestamp: '2026-04-10T10:00:00Z',
  },
  {
    id: 'msg-2',
    taskId: 'task-1',
    type: 'assistant',
    content: 'I will implement magic link authentication.',
    timestamp: '2026-04-10T10:00:01Z',
  },
];

export const mockPipeline: PipelineRun = {
  projectId: 'proj-1',
  phases: [
    { name: 'project', status: 'completed' },
    { name: 'design', status: 'completed' },
    { name: 'plan', status: 'completed' },
    { name: 'build', status: 'running' },
    { name: 'test', status: 'pending' },
    { name: 'deploy', status: 'pending' },
  ],
  currentPhase: 'build',
};

export const handlers: HttpHandler[] = [
  http.get('/api/projects', () =>
    HttpResponse.json({ data: mockProjects }),
  ),

  http.get('/api/projects/:id', ({ params }) => {
    const project = mockProjects.find((p) => p.id === params.id);
    if (!project) return HttpResponse.json({ error: 'Not found' }, { status: 404 });
    return HttpResponse.json({ data: project });
  }),

  http.get('/api/projects/:id/tasks', () =>
    HttpResponse.json({ data: mockTasks }),
  ),

  // Iterate 14.9 — useTask hook (consumed by ChatPanel for taskStatus).
  http.get('/api/projects/:projectId/tasks/:taskId', ({ params }) => {
    const task = mockTasks.find((t) => t.id === params.taskId);
    if (!task) return HttpResponse.json({ error: 'Not found' }, { status: 404 });
    return HttpResponse.json({ data: task });
  }),

  http.get('/api/tasks', () =>
    HttpResponse.json({ data: mockTasks }),
  ),

  http.get('/api/inbox', () =>
    HttpResponse.json({ data: mockInboxItems }),
  ),

  http.post('/api/inbox/:id/answer', () =>
    HttpResponse.json({ data: { ...mockInboxItems[0], status: 'answered' } }),
  ),

  http.get('/api/projects/:projectId/chat/:taskId', () =>
    HttpResponse.json({ data: mockChatMessages }),
  ),

  http.post('/api/projects/:id/chat', () =>
    HttpResponse.json({ data: { success: true } }),
  ),

  http.get('/api/projects/:id/pipeline', () =>
    HttpResponse.json({ data: mockPipeline }),
  ),

  http.get('/api/profiles', () =>
    HttpResponse.json({ data: [{ name: 'supabase-nextjs', label: 'Supabase + Next.js' }] }),
  ),

  http.get('/api/settings', () =>
    HttpResponse.json({ data: { port: 3847, maxConcurrent: 3, heartbeatIntervalMs: 30000 } }),
  ),

  http.put('/api/settings', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({ data: { port: 3847, maxConcurrent: 3, heartbeatIntervalMs: 30000, ...body } });
  }),

  http.patch('/api/projects/:id', async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>;
    const project = mockProjects.find((p) => p.id === params.id);
    return HttpResponse.json({ data: { ...project, ...body } });
  }),

  // Iterate 3.7e-b3 — Projects page queries `/api/external/tasks` to
  // derive the per-project task count column. Return an empty list so
  // tests don't log MSW "intercepted unhandled request" warnings.
  http.get('/api/external/tasks', () =>
    HttpResponse.json({ data: [] }),
  ),
];
