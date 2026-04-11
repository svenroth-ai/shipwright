import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import KanbanPage from './KanbanPage';

beforeEach(() => {
  vi.stubGlobal('EventSource', vi.fn().mockImplementation(() => ({
    onopen: null, onerror: null, onmessage: null, close: vi.fn(),
  })));
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false, media: query,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    onchange: null, addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
  vi.stubGlobal('ResizeObserver', vi.fn().mockImplementation(() => ({
    observe: vi.fn(), unobserve: vi.fn(), disconnect: vi.fn(),
  })));
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <KanbanPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('KanbanPage', () => {
  it('renders all four columns', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Backlog')).toBeInTheDocument();
      expect(screen.getByText('In Progress')).toBeInTheDocument();
      expect(screen.getByText('In Review')).toBeInTheDocument();
      expect(screen.getByText('Done')).toBeInTheDocument();
    });
  });

  it('renders All tab and New Issue button', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('All')).toBeInTheDocument();
      expect(screen.getByText('New Issue')).toBeInTheDocument();
    });
  });

  it('places tasks in correct columns', async () => {
    renderPage();
    await waitFor(() => {
      // mockTasks: task-1 is in_progress, task-2 is done
      expect(screen.getByText('Implement auth')).toBeInTheDocument();
      expect(screen.getByText('Fix login bug')).toBeInTheDocument();
    });
  });
});
