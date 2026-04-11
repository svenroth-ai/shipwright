import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ProjectTabs } from './ProjectTabs';
import type { Project } from '../../types';

const mockProjects: Project[] = [
  { id: 'p1', name: 'Alpha', path: '/a', profile: 'custom', status: 'active', lastActive: '', createdAt: '' },
  { id: 'p2', name: 'Beta', path: '/b', profile: 'custom', status: 'active', lastActive: '', createdAt: '' },
];

describe('ProjectTabs', () => {
  it('renders dropdown trigger with default label', () => {
    render(<ProjectTabs projects={mockProjects} activeProjectId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('All Projects')).toBeInTheDocument();
  });

  it('shows active project name when selected', () => {
    render(<ProjectTabs projects={mockProjects} activeProjectId="p1" onSelect={vi.fn()} />);
    expect(screen.getByText('Alpha')).toBeInTheDocument();
  });

  it('has select project aria label', () => {
    render(<ProjectTabs projects={mockProjects} activeProjectId={null} onSelect={vi.fn()} />);
    expect(screen.getByLabelText('Select project')).toBeInTheDocument();
  });
});
