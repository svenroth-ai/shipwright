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

  // Iterate 14.8.2 — gear icon aria-label preserved in 3.7e-b3 table rebuild.
  it('gear icon has aria-label "Project settings"', async () => {
    renderPage();
    await waitFor(() => {
      const gearBtn = screen.getByLabelText('Project settings');
      expect(gearBtn).toBeInTheDocument();
    });
  });

  // Iterate 3.7e-b3 — table structure.
  it('renders projects as a <table> with header row', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('projects-table')).toBeInTheDocument();
    });
    // Column headers (uppercase + displayed in the <th> cells).
    expect(screen.getByText(/Name/i)).toBeInTheDocument();
    expect(screen.getByText(/Path/i)).toBeInTheDocument();
    expect(screen.getByText(/Tasks/i)).toBeInTheDocument();
    expect(screen.getByText(/Actions/i)).toBeInTheDocument();
  });

  // Iterate 3.7e-b3 — the project row has color + path + delete affordances.
  it('renders color swatch + path + delete button for each project', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('projects-row-proj-1')).toBeInTheDocument();
    });
    expect(screen.getByTestId('projects-cell-proj-1-color')).toBeInTheDocument();
    expect(screen.getByTestId('projects-cell-proj-1-path')).toBeInTheDocument();
    expect(screen.getByTestId('projects-settings-proj-1')).toBeInTheDocument();
    expect(screen.getByTestId('projects-delete-proj-1')).toBeInTheDocument();
  });
});
