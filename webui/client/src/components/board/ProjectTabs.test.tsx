import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ProjectTabs } from './ProjectTabs';
import type { Project } from '../../types';

const mockProjects: Project[] = [
  { id: 'p1', name: 'Alpha', path: '/a', profile: 'custom', status: 'active', lastActive: '', createdAt: '' },
  { id: 'p2', name: 'Beta', path: '/b', profile: 'custom', status: 'active', lastActive: '', createdAt: '' },
];

describe('ProjectTabs', () => {
  it('renders All tab plus one per project', () => {
    render(<ProjectTabs projects={mockProjects} activeProjectId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  it('marks All tab as selected by default', () => {
    render(<ProjectTabs projects={mockProjects} activeProjectId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('All').closest('button')).toHaveAttribute('aria-selected', 'true');
  });

  it('calls onSelect with project id when tab clicked', async () => {
    const onSelect = vi.fn();
    render(<ProjectTabs projects={mockProjects} activeProjectId={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByText('Beta'));
    expect(onSelect).toHaveBeenCalledWith('p2');
  });

  it('calls onSelect with null when All tab clicked', async () => {
    const onSelect = vi.fn();
    render(<ProjectTabs projects={mockProjects} activeProjectId="p1" onSelect={onSelect} />);
    await userEvent.click(screen.getByText('All'));
    expect(onSelect).toHaveBeenCalledWith(null);
  });
});
