import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SidebarNav } from './SidebarNav';

// Section 02 (iterate 3) — SidebarNav now renders SidebarProjectList, which
// uses TanStack Query via useProjects. Every test must wrap the tree in a
// fresh QueryClientProvider so the hook doesn't throw "No QueryClient set".
function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function renderWithRouter(initialEntries = ['/']) {
  const Wrapper = makeWrapper();
  return render(
    <Wrapper>
      <MemoryRouter initialEntries={initialEntries}>
        <SidebarNav inboxCount={0} />
      </MemoryRouter>
    </Wrapper>,
  );
}

describe('SidebarNav', () => {
  beforeEach(() => {
    // Default: wide viewport
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
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

  it('renders all 4 nav items', () => {
    renderWithRouter();
    expect(screen.getByText('Task Board')).toBeInTheDocument();
    expect(screen.getByText('Projects')).toBeInTheDocument();
    expect(screen.getByText('Inbox')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('highlights active item for root route', () => {
    renderWithRouter(['/']);
    const taskBoardLink = screen.getByText('Task Board').closest('a');
    expect(taskBoardLink?.className).toContain('bg-white');
  });

  it('highlights active item for inbox route', () => {
    renderWithRouter(['/inbox']);
    const inboxLink = screen.getByText('Inbox').closest('a');
    expect(inboxLink?.className).toContain('bg-white');
  });

  it('shows inbox badge when count > 0', () => {
    const Wrapper = makeWrapper();
    render(
      <Wrapper>
        <MemoryRouter>
          <SidebarNav inboxCount={3} />
        </MemoryRouter>
      </Wrapper>,
    );
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('collapses labels on narrow viewport', () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('max-width'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    Object.defineProperty(window, 'innerWidth', { value: 600, writable: true });

    renderWithRouter();
    // Labels should be hidden (sr-only)
    const taskBoardLabel = screen.getByText('Task Board');
    expect(taskBoardLabel.className).toMatch(/sr-only/);
  });
});
