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
];
