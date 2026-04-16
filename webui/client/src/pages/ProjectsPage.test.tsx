import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ProjectsPage from './ProjectsPage';

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
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProjectsPage', () => {
  it('renders projects heading and new project button', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Projects')).toBeInTheDocument();
      expect(screen.getByText('Create Project')).toBeInTheDocument();
    });
  });

  it('renders project list from API', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Test Project')).toBeInTheDocument();
    });
  });

  // Iterate 14.8.2 — gear icon navigates with deep-link query params
  it('gear icon has aria-label "Project settings"', async () => {
    renderPage();
    await waitFor(() => {
      const gearBtn = screen.getByLabelText('Project settings');
      expect(gearBtn).toBeInTheDocument();
    });
  });
});
