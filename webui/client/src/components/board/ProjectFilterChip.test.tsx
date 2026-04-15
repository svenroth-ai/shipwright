import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ProjectFilterChip } from './ProjectFilterChip';
import type { Project } from '../../types';

const mockProjects: Project[] = [
  { id: 'p1', name: 'Alpha', path: '/a', profile: 'custom', status: 'active', lastActive: '', createdAt: '' },
  { id: 'p2', name: 'Beta', path: '/b', profile: 'custom', status: 'active', lastActive: '', createdAt: '' },
  { id: 'p3', name: 'Gamma', path: '/g', profile: 'custom', status: 'active', lastActive: '', createdAt: '' },
];

describe('ProjectFilterChip', () => {
  it('renders trigger with default "Projects" label when selection is empty', () => {
    render(
      <ProjectFilterChip
        projects={mockProjects}
        selectedProjectIds={new Set()}
        onToggle={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    const trigger = screen.getByTestId('project-filter-chip');
    expect(trigger.textContent).toContain('Projects');
    expect(trigger.textContent).not.toContain('(');
  });

  it('renders trigger with count when projects are selected', () => {
    render(
      <ProjectFilterChip
        projects={mockProjects}
        selectedProjectIds={new Set(['p1', 'p2'])}
        onToggle={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    const trigger = screen.getByTestId('project-filter-chip');
    expect(trigger.textContent).toContain('Projects (2)');
  });

  it('clicking the trigger opens the popover and shows project rows with color dots', () => {
    render(
      <ProjectFilterChip
        projects={mockProjects}
        selectedProjectIds={new Set()}
        onToggle={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('project-filter-chip'));
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
    expect(screen.getByTestId('project-color-dot-p1')).toBeInTheDocument();
    expect(screen.getByTestId('project-color-dot-p2')).toBeInTheDocument();
  });

  it('clicking a checkbox fires onToggle with the project id', () => {
    const onToggle = vi.fn();
    render(
      <ProjectFilterChip
        projects={mockProjects}
        selectedProjectIds={new Set()}
        onToggle={onToggle}
        onClear={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('project-filter-chip'));
    const alphaLabel = screen.getByText('Alpha').closest('label');
    const checkbox = alphaLabel?.querySelector('input[type="checkbox"]');
    expect(checkbox).toBeTruthy();
    fireEvent.click(checkbox as HTMLInputElement);
    expect(onToggle).toHaveBeenCalledWith('p1');
  });
});
