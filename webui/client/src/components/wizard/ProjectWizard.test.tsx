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
    await userEvent.type(screen.getByPlaceholderText(/home/), '/tmp/test');
    await userEvent.click(screen.getByText('Next'));
    expect(screen.getByText('Stack & Profile')).toBeInTheDocument();
  });

  it('disables Next when name is empty', () => {
    renderWizard();
    expect(screen.getByText('Next')).toBeDisabled();
  });
});
