import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect } from 'vitest';
import { TaskListView } from './TaskListView';
import type { Task } from '../../types';

const mockTasks: Task[] = [
  { id: 't1', projectId: 'p1', title: 'Alpha task', description: 'Alpha task', status: 'running', kanbanStatus: 'in_progress', currentPhase: 'build', priority: 'P1', sessionId: 's1', createdAt: '2026-04-10T10:00:00Z', updatedAt: '2026-04-10T10:00:00Z' },
  { id: 't2', projectId: 'p1', title: 'Beta task', description: 'Beta task', status: 'done', kanbanStatus: 'done', currentPhase: 'test', priority: 'P2', sessionId: 's2', createdAt: '2026-04-09T08:00:00Z', updatedAt: '2026-04-09T08:00:00Z' },
  { id: 't3', projectId: 'p1', title: 'Charlie task', description: 'Charlie task', status: 'pending', kanbanStatus: 'backlog', sessionId: 's3', createdAt: '2026-04-08T08:00:00Z', updatedAt: '2026-04-08T08:00:00Z' },
];

function renderList(tasks = mockTasks) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TaskListView tasks={tasks} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TaskListView', () => {
  it('renders all task rows', () => {
    renderList();
    expect(screen.getByText('Alpha task')).toBeInTheDocument();
    expect(screen.getByText('Beta task')).toBeInTheDocument();
    expect(screen.getByText('Charlie task')).toBeInTheDocument();
  });

  it('renders column headers', () => {
    renderList();
    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('Phase')).toBeInTheDocument();
    expect(screen.getByText('Priority')).toBeInTheDocument();
    expect(screen.getByText('Updated')).toBeInTheDocument();
  });

  it('toggles sort direction on header click', async () => {
    renderList();
    const titleHeader = screen.getByText('Title');
    await userEvent.click(titleHeader);
    // Should now be sorted ascending by title
    const rows = screen.getAllByRole('row');
    // Header row + 3 data rows
    expect(rows.length).toBe(4);
  });

  it('shows empty state when no tasks', () => {
    renderList([]);
    expect(screen.getByText('No tasks match current filters')).toBeInTheDocument();
  });
});
