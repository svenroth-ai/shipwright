import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import InboxPage from './InboxPage';

beforeEach(() => {
  vi.stubGlobal('EventSource', vi.fn().mockImplementation(() => ({
    onopen: null, onerror: null, onmessage: null, close: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <InboxPage />
    </QueryClientProvider>,
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
});
