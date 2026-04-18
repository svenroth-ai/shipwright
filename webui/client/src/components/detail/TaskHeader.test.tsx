import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Task } from '../../types';

// Iterate 14.11 — mock api module for the resume-button click test.
// Must be hoisted (vi.mock is lifted above imports), so the stubbed
// apiPost / apiPatch can be asserted on.
const apiPostSpy = vi.fn<(path: string, body: unknown) => Promise<unknown>>(
  async () => ({}),
);
const apiPatchSpy = vi.fn<(path: string, body: unknown) => Promise<unknown>>(
  async () => ({}),
);
vi.mock('../../lib/api', () => ({
  apiPost: (path: string, body: unknown) => apiPostSpy(path, body),
  apiPatch: (path: string, body: unknown) => apiPatchSpy(path, body),
  apiFetch: vi.fn(async () => ({})),
}));

import { TaskHeader } from './TaskHeader';

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
  beforeEach(() => {
    apiPostSpy.mockClear();
    apiPatchSpy.mockClear();
  });

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

  // Iterate 14.11 — header pause indicator + Resume button
  describe('interrupted task affordance', () => {
    const interruptedTask: Task = {
      ...mockTask,
      status: 'orphaned',
      orphanReason: 'stale_on_startup',
      claudeSessionId: 'claude-session-abc',
    };

    it('renders pause indicator + Resume button when task is interrupted', () => {
      renderHeader(interruptedTask);
      expect(screen.getByTestId('header-pause-indicator')).toBeInTheDocument();
      expect(screen.getByTestId('header-resume-button')).toBeInTheDocument();
      expect(screen.getByText(/Task interrupted/)).toBeInTheDocument();
    });

    it('hides pause indicator when task is running', () => {
      renderHeader(mockTask);
      expect(screen.queryByTestId('header-pause-indicator')).toBeNull();
      expect(screen.queryByTestId('header-resume-button')).toBeNull();
    });

    it('hides pause indicator when orphaned but missing claudeSessionId', () => {
      renderHeader({ ...interruptedTask, claudeSessionId: undefined });
      expect(screen.queryByTestId('header-pause-indicator')).toBeNull();
    });

    // Iterate modelswitch-uat-round2 (2026-04-18) — widen the gate. Any
    // orphan reason with a captured sessionId is resumable, not just the
    // 14.11 narrow list (stale_on_startup | user_interrupted).
    it('renders Resume for orphan reasons outside the 14.11 narrow list (e.g. switch_timeout)', () => {
      renderHeader({
        ...interruptedTask,
        orphanReason: 'switch_timeout' as string,
      });
      expect(screen.getByTestId('header-pause-indicator')).toBeInTheDocument();
      expect(screen.getByTestId('header-resume-button')).toBeInTheDocument();
    });

    it('renders Resume for orphaned task with no orphanReason set', () => {
      renderHeader({ ...interruptedTask, orphanReason: undefined });
      expect(screen.getByTestId('header-pause-indicator')).toBeInTheDocument();
    });

    it('fires resume mutation when Resume button is clicked', async () => {
      renderHeader(interruptedTask);
      fireEvent.click(screen.getByTestId('header-resume-button'));
      await waitFor(() => {
        expect(apiPostSpy).toHaveBeenCalledWith(
          '/projects/proj-1/tasks/task-1/resume',
          {},
        );
      });
    });
  });
});
