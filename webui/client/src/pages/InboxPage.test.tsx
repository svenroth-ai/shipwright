import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import InboxPage from './InboxPage';
import { server } from '../test/mocks/server';

// Iterate 14.7.1 — stub useNavigate so we can assert inbox-item click fires
// the correct deep-link URL without mounting a real router tree.
const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

beforeEach(() => {
  navigateMock.mockReset();
  vi.stubGlobal('EventSource', vi.fn().mockImplementation(() => ({
    onopen: null, onerror: null, onmessage: null, close: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <InboxPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('InboxPage', () => {
  it('renders inbox heading', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Inbox')).toBeInTheDocument();
    });
  });

  it('renders pending questions from API', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Which auth provider?')).toBeInTheDocument();
    });
  });

  // ──────────────────────────────────────────────────────────────
  // Iterate 14.5 — notBlocked warning icon in inbox list
  // ──────────────────────────────────────────────────────────────

  it('does NOT render the notBlocked icon when flag is absent', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Which auth provider?')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('inbox-not-blocked-icon')).toBeNull();
  });

  // ──────────────────────────────────────────────────────────────
  // Iterate 14.7.1 — clickable inbox items navigate to task chat
  // ──────────────────────────────────────────────────────────────

  it('navigates to the task chat when the outer item card is clicked', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Which auth provider?')).toBeInTheDocument();
    });
    const card = screen.getByTestId('inbox-item-inbox-1');
    fireEvent.click(card);
    expect(navigateMock).toHaveBeenCalledWith(
      '/projects/proj-1/tasks/task-1?focus=chat-bottom',
    );
  });

  it('does NOT navigate when the inner Answer button is clicked', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Which auth provider?')).toBeInTheDocument();
    });
    // Pre-fill the answer by clicking an option (inside card, also
    // stopPropagation) so the Answer button is enabled.
    const supabaseChip = screen.getByText('Supabase');
    fireEvent.click(supabaseChip);
    // Clicking the Answer button must NOT propagate to the item card.
    const answerBtn = screen.getByTestId('inbox-answer-inbox-1');
    fireEvent.click(answerBtn);
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('renders the notBlocked warning icon when item has notBlocked=true', async () => {
    server.use(
      http.get('/api/inbox', () =>
        HttpResponse.json({
          data: [
            {
              id: 'inbox-flagged',
              projectId: 'proj-1',
              taskId: 'task-1',
              parts: [{ question: 'Was ignored?' }],
              status: 'pending',
              createdAt: '2026-04-14T10:00:00Z',
              notBlocked: true,
            },
          ],
        }),
      ),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Was ignored?')).toBeInTheDocument();
    });
    expect(screen.getByTestId('inbox-not-blocked-icon')).toBeInTheDocument();
  });
});
