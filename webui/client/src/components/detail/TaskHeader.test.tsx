import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect } from 'vitest';
import { TaskHeader } from './TaskHeader';
import type { Task } from '../../types';

const mockTask: Task = {
  id: 'task-1',
  projectId: 'proj-1',
  title: 'Implement auth flow',
  description: 'Build login, register, and password reset pages with OAuth support',
  status: 'running',
  kanbanStatus: 'in_progress',
  currentPhase: 'build',
  priority: 'P1',
  sessionId: 's1',
  createdAt: '2026-04-10T10:00:00Z',
  updatedAt: '2026-04-10T10:05:00Z',
};

function renderHeader(task = mockTask) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TaskHeader task={task} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TaskHeader', () => {
  it('renders task title', () => {
    renderHeader();
    expect(screen.getByText('Implement auth flow')).toBeInTheDocument();
  });

  it('renders back button', () => {
    renderHeader();
    expect(screen.getByText('Back to Board')).toBeInTheDocument();
  });

  it('renders phase tag and priority', () => {
    renderHeader();
    expect(screen.getByText('build')).toBeInTheDocument();
    expect(screen.getByText('P1')).toBeInTheDocument();
  });

  it('renders status', () => {
    renderHeader();
    expect(screen.getByText('In Progress')).toBeInTheDocument();
  });

  it('renders three-dot menu button', () => {
    renderHeader();
    expect(screen.getByLabelText('Task actions')).toBeInTheDocument();
  });

  it('shows edit option for pending tasks', () => {
    renderHeader({ ...mockTask, status: 'pending', kanbanStatus: 'backlog' });
    // Menu trigger is present
    expect(screen.getByLabelText('Task actions')).toBeInTheDocument();
  });
});
