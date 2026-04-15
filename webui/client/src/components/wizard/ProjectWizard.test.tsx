import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { ProjectWizard } from './ProjectWizard';

function renderWizard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProjectWizard open onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('ProjectWizard', () => {
  it('renders step 1 with name and path fields', () => {
    renderWizard();
    expect(screen.getByText('New Project')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('My Awesome App')).toBeInTheDocument();
    expect(screen.getByText('Project Info')).toBeInTheDocument();
  });

  it('navigates to step 2 on Next', async () => {
    renderWizard();
    await userEvent.type(screen.getByPlaceholderText('My Awesome App'), 'Test');
    // Path input placeholder changed
    const pathInput = screen.getByPlaceholderText(/Users|home|projects/);
    await userEvent.type(pathInput, '/tmp/test');
    await userEvent.click(screen.getByText('Next'));
    expect(screen.getByText('Stack & Profile')).toBeInTheDocument();
  });

  it('disables Next when name is empty', () => {
    renderWizard();
    expect(screen.getByText('Next')).toBeDisabled();
  });

  // Iterate 14.7.1 — the old "Browse" button was renamed to "Paste" (the
  // File System Access API never returned a usable absolute path; we now
  // paste from the clipboard instead).
  it('shows paste button for the project directory field', () => {
    renderWizard();
    expect(screen.getByTestId('project-path-paste')).toBeInTheDocument();
    expect(screen.getByText('Paste')).toBeInTheDocument();
  });
});
