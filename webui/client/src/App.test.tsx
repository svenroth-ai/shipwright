import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App';

beforeEach(() => {
  // Mock EventSource for useSSE
  vi.stubGlobal('EventSource', vi.fn().mockImplementation(() => ({
    onopen: null,
    onerror: null,
    onmessage: null,
    close: vi.fn(),
  })));
  // Mock matchMedia for sidebar
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
}

describe('App', () => {
  it('renders without crashing and displays sidebar', () => {
    const queryClient = createTestQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    expect(screen.getByText('Shipwright')).toBeInTheDocument();
    expect(screen.getAllByText('Task Board').length).toBeGreaterThanOrEqual(1);
  });
});
