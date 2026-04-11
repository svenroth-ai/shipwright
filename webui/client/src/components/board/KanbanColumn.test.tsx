import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeAll } from 'vitest';
import { KanbanColumn } from './KanbanColumn';
import type { Task } from '../../types';

const baseTasks: Task[] = [
  { id: 't1', projectId: 'p1', title: 'Task One', description: 'Task One', status: 'pending', kanbanStatus: 'backlog', sessionId: 's1', createdAt: '', updatedAt: '' },
  { id: 't2', projectId: 'p1', title: 'Task Two', description: 'Task Two', status: 'pending', kanbanStatus: 'backlog', sessionId: 's2', createdAt: '', updatedAt: '' },
];

function renderColumn(tasks: Task[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <KanbanColumn title="Backlog" tasks={tasks} status="backlog" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', vi.fn().mockImplementation(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  })));
});

describe('KanbanColumn', () => {
  it('renders header with name and count', () => {
    renderColumn(baseTasks);
    expect(screen.getByText('Backlog')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('renders task cards', () => {
    renderColumn(baseTasks);
    expect(screen.getByText('Task One')).toBeInTheDocument();
    expect(screen.getByText('Task Two')).toBeInTheDocument();
  });

  it('shows empty state when no tasks', () => {
    renderColumn([]);
    expect(screen.getByText('No tasks')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
  });
});
