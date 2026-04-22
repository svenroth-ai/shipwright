/*
 * Iterate 3.7e-b3 (2026-04-22) — ProjectSettingsDialog smoke tests.
 *
 * Covers: render with a project, name input seeded, path read-only, color
 * picker present, error banner shows on 500.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/mocks/server';
import { ProjectSettingsDialog } from './ProjectSettingsDialog';
import type { Project } from '../../types';

const TEST_PROJECT: Project = {
  id: 'proj-1',
  name: 'Test Project',
  path: '/tmp/test-project',
  profile: 'custom',
  status: 'active',
  lastActive: '2026-04-10T10:00:00Z',
  createdAt: '2026-04-01T00:00:00Z',
  settings: { color: '#B8A590' },
};

function renderDialog(project: Project | null = TEST_PROJECT) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProjectSettingsDialog project={project} open onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('ProjectSettingsDialog', () => {
  it('renders name field seeded from project', () => {
    renderDialog();
    const nameInput = screen.getByTestId('project-settings-name') as HTMLInputElement;
    expect(nameInput.value).toBe('Test Project');
  });

  it('displays path read-only', () => {
    renderDialog();
    const pathDisplay = screen.getByTestId('project-settings-path');
    expect(pathDisplay).toHaveTextContent('/tmp/test-project');
    // It's a div, not an input — no form submission for path.
    expect(pathDisplay.tagName.toLowerCase()).toBe('div');
  });

  it('color picker reflects current color selection', () => {
    renderDialog();
    const selectedSwatch = screen.getByTestId('project-settings-color-b8a590');
    expect(selectedSwatch).toHaveAttribute('data-selected', 'true');
  });

  it('shows error banner on PATCH failure and keeps dialog open', async () => {
    server.use(
      http.patch('/api/projects/:id', () =>
        HttpResponse.json(
          { error: 'EACCES: permission denied' },
          { status: 500 },
        ),
      ),
    );
    renderDialog();
    await userEvent.click(screen.getByTestId('project-settings-save'));
    await waitFor(() => {
      expect(screen.getByTestId('project-settings-error')).toBeInTheDocument();
    });
    // Dialog root still in DOM — save did not close it.
    expect(screen.getByTestId('project-settings-dialog')).toBeInTheDocument();
  });
});
