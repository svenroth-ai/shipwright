export const queryKeys = {
  projects: {
    all: ['projects'] as const,
    detail: (id: string) => ['projects', id] as const,
  },
  tasks: {
    all: ['tasks'] as const,
    byProject: (projectId: string) => ['tasks', projectId] as const,
    detail: (projectId: string, taskId: string) => ['tasks', projectId, taskId] as const,
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
