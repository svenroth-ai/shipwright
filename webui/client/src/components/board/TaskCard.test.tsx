import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import type { Task } from '../../types';

// Iterate 14.7.0 — mock api module for the resume-button click test.
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

import { TaskCard } from './TaskCard';

const mockTask: Task = {
  id: 'task-abc1234',
  projectId: 'proj-1',
  title: 'Implement magic link authentication',
  description: 'Implement magic link authentication',
  status: 'running',
  kanbanStatus: 'in_progress',
  currentPhase: 'build',
  priority: 'P1',
  sessionId: 'session-1',
  createdAt: '2026-04-10T10:00:00Z',
  updatedAt: '2026-04-10T10:05:00Z',
};

function renderWithProviders(task: Task, showProjectStrip = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TaskCard task={task} showProjectStrip={showProjectStrip} />
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

// Iterate 14.7.0 — interrupted state rendering (P0.0)
describe('TaskCard — interrupted state', () => {
  const interruptedTask: Task = {
    ...mockTask,
    id: 'task-interrupted',
    status: 'orphaned',
    kanbanStatus: 'interrupted',
    orphanReason: 'stale_on_startup',
    claudeSessionId: 'real-claude-sess-abc',
  };

  beforeEach(() => {
    apiPostSpy.mockClear();
    apiPatchSpy.mockClear();
  });

  it('renders pause icon when kanbanStatus is interrupted', () => {
    renderWithProviders(interruptedTask);
    expect(screen.getByTestId('interrupted-pause-icon')).toBeInTheDocument();
  });

  it('renders Resume and Cancel action buttons for interrupted tasks', () => {
    renderWithProviders(interruptedTask);
    expect(screen.getByTestId('resume-task-button')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-interrupted-button')).toBeInTheDocument();
  });

  it('does NOT render pause icon for non-interrupted tasks', () => {
    renderWithProviders(mockTask);
    expect(screen.queryByTestId('interrupted-pause-icon')).not.toBeInTheDocument();
    expect(screen.queryByTestId('resume-task-button')).not.toBeInTheDocument();
  });

  it('clicking Resume fires a POST to the resume endpoint', async () => {
    renderWithProviders(interruptedTask);
    const btn = screen.getByTestId('resume-task-button');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(apiPostSpy).toHaveBeenCalledWith(
        `/projects/${interruptedTask.projectId}/tasks/${interruptedTask.id}/resume`,
        {},
      );
    });
  });
});

// Iterate 14.7.2 — multi-project kanban left-edge strip
describe('TaskCard — project strip (All Projects view)', () => {
  it('renders project strip when showProjectStrip is true and projectId is present', () => {
    renderWithProviders(mockTask, true);
    const strip = screen.getByTestId('project-strip');
    expect(strip).toBeInTheDocument();
    // Strip must carry a backgroundColor from the project color helper.
    // jsdom normalises hsl(...) inline styles to rgb(...), so we assert
    // on the computed style value instead of the raw attribute.
    expect((strip as HTMLElement).style.backgroundColor).not.toBe('');
  });

  it('does NOT render project strip when showProjectStrip is false (single project mode)', () => {
    renderWithProviders(mockTask, false);
    expect(screen.queryByTestId('project-strip')).not.toBeInTheDocument();
  });

  it('phase tag renders in monochrome (grey) when showProjectStrip is true', () => {
    renderWithProviders(mockTask, true);
    const tag = screen.getByText('build');
    expect(tag.className).toContain('bg-gray-100');
    expect(tag.className).not.toContain('bg-orange-50');
  });
});
