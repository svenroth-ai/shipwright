import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SidebarNav } from './SidebarNav';

function renderWithRouter(initialEntries = ['/']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <SidebarNav inboxCount={0} />
    </MemoryRouter>,
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
    expect(taskBoardLink?.className).toMatch(/active/);
  });

  it('highlights active item for inbox route', () => {
    renderWithRouter(['/inbox']);
    const inboxLink = screen.getByText('Inbox').closest('a');
    expect(inboxLink?.className).toMatch(/active/);
  });

  it('shows inbox badge when count > 0', () => {
    render(
      <MemoryRouter>
        <SidebarNav inboxCount={3} />
      </MemoryRouter>,
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
