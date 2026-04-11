import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { StatusIcon } from './StatusIcon';
import type { KanbanStatus } from '../../types';

const statuses: KanbanStatus[] = ['backlog', 'in_progress', 'in_review', 'done', 'failed', 'cancelled'];

describe('StatusIcon', () => {
  it.each(statuses)('renders icon with aria-label for %s status', (status) => {
    render(<StatusIcon status={status} />);
    const icon = screen.getByLabelText(/.+/);
    expect(icon).toBeInTheDocument();
  });

  it('renders correct label for done status', () => {
    render(<StatusIcon status="done" />);
    expect(screen.getByLabelText('Done')).toBeInTheDocument();
  });

  it('renders correct label for in_progress status', () => {
    render(<StatusIcon status="in_progress" />);
    expect(screen.getByLabelText('In Progress')).toBeInTheDocument();
  });
});
