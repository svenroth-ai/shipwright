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
    // Phase B5 — step label is now "Step 1 of 4 — Project Info" (one span).
    expect(screen.getByText(/Step 1 of 4/)).toBeInTheDocument();
    expect(screen.getByText(/Project Info/)).toBeInTheDocument();
  });

  it('navigates to step 2 on Next', async () => {
    renderWizard();
    await userEvent.type(screen.getByPlaceholderText('My Awesome App'), 'Test');
    // Path input placeholder changed
    const pathInput = screen.getByPlaceholderText(/Users|home|projects/);
    await userEvent.type(pathInput, '/tmp/test');
    await userEvent.click(screen.getByTestId('wizard-next'));
    // Phase B5 — step label contains "Stack & Profile"; match it via regex.
    expect(screen.getByText(/Stack & Profile/)).toBeInTheDocument();
  });

  it('disables Next when name is empty', () => {
    renderWizard();
    expect(screen.getByTestId('wizard-next')).toBeDisabled();
  });

  // Iterate 14.7.1 — the old "Browse" button was renamed to "Paste" (the
  // File System Access API never returned a usable absolute path; we now
  // paste from the clipboard instead).
  it('shows paste button for the project directory field', () => {
    renderWizard();
    expect(screen.getByTestId('project-path-paste')).toBeInTheDocument();
    expect(screen.getByText('Paste')).toBeInTheDocument();
  });

  // Iterate 3.7e-b3 — color picker appears on the confirmation step so a
  // color can be set at create time. Navigate wizard to step 3 (index 3).
  it('shows color picker on confirmation step', async () => {
    renderWizard();
    await userEvent.type(screen.getByPlaceholderText('My Awesome App'), 'Test');
    const pathInput = screen.getByPlaceholderText(/Users|home|projects/);
    await userEvent.type(pathInput, '/tmp/test');
    // Step 1 → Step 2
    await userEvent.click(screen.getByTestId('wizard-next'));
    // Step 2 → Step 3
    await userEvent.click(screen.getByTestId('wizard-next'));
    // Step 3 → Step 4 (confirmation)
    await userEvent.click(screen.getByTestId('wizard-next'));
    expect(screen.getByTestId('wizard-color-section')).toBeInTheDocument();
    expect(screen.getByTestId('project-color-picker')).toBeInTheDocument();
    // Auto swatch is preset by default.
    const autoSwatch = screen.getByTestId('wizard-color-swatch-auto');
    expect(autoSwatch).toHaveAttribute('data-selected', 'true');
  });
});
