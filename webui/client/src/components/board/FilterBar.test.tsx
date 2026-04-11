import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { FilterBar } from './FilterBar';

function renderFilterBar(overrides = {}) {
  const defaults = {
    selectedPhases: [] as string[],
    togglePhase: vi.fn(),
    clearPhases: vi.fn(),
    selectedPriority: null as string | null,
    setPriority: vi.fn(),
    viewMode: 'board' as const,
    setViewMode: vi.fn(),
    ...overrides,
  };
  return render(<FilterBar {...defaults} />);
}

describe('FilterBar', () => {
  it('renders phase and priority filter buttons', () => {
    renderFilterBar();
    expect(screen.getByText('Phase')).toBeInTheDocument();
    expect(screen.getByText('Priority')).toBeInTheDocument();
  });

  it('renders view toggle with Board and List', () => {
    renderFilterBar();
    expect(screen.getByLabelText('Board view')).toBeInTheDocument();
    expect(screen.getByLabelText('List view')).toBeInTheDocument();
  });

  it('shows filter chips when filters are active', () => {
    renderFilterBar({ selectedPhases: ['build', 'test'], selectedPriority: 'P1' });
    // Filter chips have remove buttons
    expect(screen.getByLabelText('Remove build filter')).toBeInTheDocument();
    expect(screen.getByLabelText('Remove test filter')).toBeInTheDocument();
    expect(screen.getByLabelText('Remove P1 filter')).toBeInTheDocument();
  });

  it('hides filter chips when no filters active', () => {
    const { container } = renderFilterBar();
    // No filter chips rendered — only the filter buttons exist
    expect(container.querySelectorAll('[aria-label^="Remove"]').length).toBe(0);
  });
});
