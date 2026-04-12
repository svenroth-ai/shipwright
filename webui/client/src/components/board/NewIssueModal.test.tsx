import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NewIssueModal } from './NewIssueModal';
import type { Project } from '../../types';

const apiPostMock = vi.fn();

vi.mock('../../lib/api', () => ({
  apiPost: (...args: unknown[]) => apiPostMock(...args),
}));

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
  beforeEach(() => {
    apiPostMock.mockReset();
    // Default: classify responds with "design"; task POST returns an id.
    apiPostMock.mockImplementation((path: string) => {
      if (path.includes('/classify')) {
        return Promise.resolve({ phase: 'design', phase_confidence: 0.8 });
      }
      return Promise.resolve({ id: 't1' });
    });
  });

  it('renders title and description fields when open', () => {
    renderModal();
    expect(screen.getByLabelText('Title')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
  });

  it('submit button is disabled when title is empty', () => {
    renderModal();
    expect(screen.getByText('Create Task')).toBeDisabled();
  });

  it('submit button enables when title has content', async () => {
    renderModal();
    await userEvent.type(screen.getByLabelText('Title'), 'Fix login');
    expect(screen.getByText('Create Task')).toBeEnabled();
  });

  it('shows project selector when activeProjectId is null', () => {
    renderModal({ activeProjectId: null });
    expect(screen.getByText('Select a project...')).toBeInTheDocument();
  });

  it('hides project selector when activeProjectId is set', () => {
    renderModal({ activeProjectId: 'p1' });
    expect(screen.queryByText('Select a project...')).not.toBeInTheDocument();
  });

  it('renders phase dropdown with 8 options', () => {
    renderModal();
    const dropdown = screen.getByLabelText(/Phase/) as HTMLSelectElement;
    expect(dropdown).toBeInTheDocument();
    expect(dropdown.options).toHaveLength(8);
  });

  it('auto-suggests phase from classify endpoint and shows sparkle', async () => {
    renderModal();
    await userEvent.type(screen.getByLabelText('Title'), 'design a landing page');

    await waitFor(
      () => {
        const dropdown = screen.getByLabelText(/Phase/) as HTMLSelectElement;
        expect(dropdown.value).toBe('design');
      },
      { timeout: 2000 },
    );
    // Sparkle/auto indicator visible
    expect(screen.getByText('auto')).toBeInTheDocument();

    // Verify classify was called with the typed description
    const classifyCall = apiPostMock.mock.calls.find(([path]) => typeof path === 'string' && path.includes('/classify'));
    expect(classifyCall).toBeDefined();
    expect(classifyCall![1]).toMatchObject({ description: expect.stringContaining('design a landing page') });
  });

  it('manual phase override removes the auto sparkle', async () => {
    renderModal();
    await userEvent.type(screen.getByLabelText('Title'), 'design a landing page');

    await waitFor(() => {
      expect((screen.getByLabelText(/Phase/) as HTMLSelectElement).value).toBe('design');
    }, { timeout: 2000 });

    await userEvent.selectOptions(screen.getByLabelText(/Phase/), 'build');
    expect((screen.getByLabelText(/Phase/) as HTMLSelectElement).value).toBe('build');
    expect(screen.queryByText('auto')).not.toBeInTheDocument();
  });

  it('submits the selected phase in the POST /tasks body', async () => {
    renderModal();
    await userEvent.type(screen.getByLabelText('Title'), 'Fix login bug');
    await userEvent.selectOptions(screen.getByLabelText(/Phase/), 'test');
    await userEvent.click(screen.getByText('Create Task'));

    await waitFor(() => {
      const taskPost = apiPostMock.mock.calls.find(
        ([path]) => typeof path === 'string' && path.includes('/tasks') && !path.includes('/classify'),
      );
      expect(taskPost).toBeDefined();
      expect(taskPost![1]).toMatchObject({ phase: 'test', title: 'Fix login bug' });
    });
  });
});
