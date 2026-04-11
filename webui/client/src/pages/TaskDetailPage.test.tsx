import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TaskDetailPage from './TaskDetailPage';

beforeEach(() => {
  vi.stubGlobal('EventSource', vi.fn().mockImplementation(() => ({
    onopen: null, onerror: null, onmessage: null, close: vi.fn(),
  })));
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false, media: query,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    onchange: null, addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
});

function renderPage(taskId = 'task-1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/tasks/${taskId}`]}>
        <Routes>
          <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TaskDetailPage', () => {
  it('renders task header and panels when task found', async () => {
    renderPage('task-1');
    await waitFor(() => {
      expect(screen.getByText('Implement auth')).toBeInTheDocument();
    });
    expect(screen.getByText('Back to Board')).toBeInTheDocument();
    expect(screen.getByTestId('viewer-slot')).toBeInTheDocument();
  });

  it('shows task not found for invalid taskId', async () => {
    renderPage('nonexistent');
    await waitFor(() => {
      expect(screen.getByText('Task not found')).toBeInTheDocument();
    });
  });
});
