import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CardEnrichment } from './CardEnrichment';
import type { Task } from '../../types';

const baseTask: Task = {
  id: 't1', projectId: 'p1', title: 'Test', description: 'Test', status: 'pending',
  kanbanStatus: 'backlog', sessionId: 's1',
  createdAt: new Date(Date.now() - 60_000).toISOString(),
  updatedAt: new Date().toISOString(),
};

describe('CardEnrichment', () => {
  it('shows intent and complexity when present', () => {
    render(<CardEnrichment task={{ ...baseTask, intent: 'feat', complexity: 'medium' }} />);
    expect(screen.getByText('feat')).toBeInTheDocument();
    expect(screen.getByText('medium')).toBeInTheDocument();
  });

  it('shows classifying for recent tasks without intent', () => {
    const recentTask = { ...baseTask, createdAt: new Date().toISOString() };
    render(<CardEnrichment task={recentTask} />);
    expect(screen.getByText('Classifying...')).toBeInTheDocument();
  });
});
