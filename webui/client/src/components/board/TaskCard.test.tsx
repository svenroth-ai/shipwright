import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeAll } from 'vitest';
import { TaskCard } from './TaskCard';
import type { Task } from '../../types';

const mockTask: Task = {
  id: 'task-abc1234',
  projectId: 'proj-1',
  description: 'Implement magic link authentication',
  status: 'running',
  kanbanStatus: 'in_progress',
  currentPhase: 'build',
  priority: 'P1',
  sessionId: 'session-1',
  createdAt: '2026-04-10T10:00:00Z',
  updatedAt: '2026-04-10T10:05:00Z',
};

function renderWithProviders(task: Task) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TaskCard task={task} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Suppress Radix portal warnings in test
beforeAll(() => {
  vi.stubGlobal('ResizeObserver', vi.fn().mockImplementation(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  })));
});

describe('TaskCard', () => {
  it('renders task title', () => {
    renderWithProviders(mockTask);
    expect(screen.getByText('Implement magic link authentication')).toBeInTheDocument();
  });

  it('renders phase tag', () => {
    renderWithProviders(mockTask);
    expect(screen.getByText('build')).toBeInTheDocument();
  });

  it('renders priority indicator', () => {
    renderWithProviders(mockTask);
    expect(screen.getByText('P1')).toBeInTheDocument();
  });

  it('renders commit hash prefix', () => {
    renderWithProviders(mockTask);
    expect(screen.getByText('#task-ab')).toBeInTheDocument();
  });

  it('renders overflow menu button', () => {
    renderWithProviders(mockTask);
    expect(screen.getByLabelText('Task actions')).toBeInTheDocument();
  });
});
