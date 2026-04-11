import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import { TaskHeader } from './TaskHeader';
import type { Task } from '../../types';

const mockTask: Task = {
  id: 'task-1',
  projectId: 'proj-1',
  description: 'Implement auth flow',
  status: 'running',
  kanbanStatus: 'in_progress',
  currentPhase: 'build',
  priority: 'P1',
  sessionId: 's1',
  createdAt: '2026-04-10T10:00:00Z',
  updatedAt: '2026-04-10T10:05:00Z',
};

describe('TaskHeader', () => {
  it('renders task title', () => {
    render(<MemoryRouter><TaskHeader task={mockTask} /></MemoryRouter>);
    expect(screen.getByText('Implement auth flow')).toBeInTheDocument();
  });

  it('renders back button', () => {
    render(<MemoryRouter><TaskHeader task={mockTask} /></MemoryRouter>);
    expect(screen.getByText('Back to Board')).toBeInTheDocument();
  });

  it('renders phase tag and priority', () => {
    render(<MemoryRouter><TaskHeader task={mockTask} /></MemoryRouter>);
    expect(screen.getByText('build')).toBeInTheDocument();
    expect(screen.getByText('P1')).toBeInTheDocument();
  });

  it('renders status', () => {
    render(<MemoryRouter><TaskHeader task={mockTask} /></MemoryRouter>);
    expect(screen.getByText('In Progress')).toBeInTheDocument();
  });
});
