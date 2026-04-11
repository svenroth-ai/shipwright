import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MainLayout } from './MainLayout';

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

describe('MainLayout', () => {
  it('renders sidebar and outlet content', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <MainLayout />,
          children: [
            { index: true, element: <div>Page Content</div> },
          ],
        },
      ],
      { initialEntries: ['/'] },
    );

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(screen.getByText('Shipwright')).toBeInTheDocument();
    expect(screen.getByText('Page Content')).toBeInTheDocument();
  });
});
