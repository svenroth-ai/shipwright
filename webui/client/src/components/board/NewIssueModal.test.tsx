import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { NewIssueModal } from './NewIssueModal';
import type { Project } from '../../types';

const mockProjects: Project[] = [
  { id: 'p1', name: 'Alpha', path: '/a', profile: 'custom', status: 'active', lastActive: '', createdAt: '' },
];

function renderModal(props: Partial<React.ComponentProps<typeof NewIssueModal>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    activeProjectId: 'p1' as string | null,
    projects: mockProjects,
    ...props,
  };
  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <NewIssueModal {...defaultProps} />
      </QueryClientProvider>,
    ),
    onOpenChange: defaultProps.onOpenChange,
  };
}

describe('NewIssueModal', () => {
  it('renders title and description fields when open', () => {
    renderModal();
    expect(screen.getByLabelText('Title')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
  });

  it('submit button is disabled when title is empty', () => {
    renderModal();
    expect(screen.getByText('Create Issue')).toBeDisabled();
  });

  it('submit button enables when title has content', async () => {
    renderModal();
    await userEvent.type(screen.getByLabelText('Title'), 'Fix login');
    expect(screen.getByText('Create Issue')).toBeEnabled();
  });

  it('shows project selector when activeProjectId is null', () => {
    renderModal({ activeProjectId: null });
    expect(screen.getByText('Select a project...')).toBeInTheDocument();
  });

  it('hides project selector when activeProjectId is set', () => {
    renderModal({ activeProjectId: 'p1' });
    expect(screen.queryByText('Select a project...')).not.toBeInTheDocument();
  });
});
