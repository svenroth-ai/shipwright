import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { FilterBar } from './FilterBar';

function renderFilterBar(overrides = {}) {
  const defaults = {
    selectedPhases: [] as string[],
    togglePhase: vi.fn(),
    clearPhases: vi.fn(),
    viewMode: 'board' as const,
    setViewMode: vi.fn(),
    ...overrides,
  };
  return render(<FilterBar {...defaults} />);
}

describe('FilterBar', () => {
  it('renders phase filter button', () => {
    renderFilterBar();
    expect(screen.getByText('Phase')).toBeInTheDocument();
  });

  it('does not render a priority filter', () => {
    renderFilterBar();
    expect(screen.queryByText('Priority')).not.toBeInTheDocument();
  });

  it('renders view toggle with Board and List', () => {
    renderFilterBar();
    expect(screen.getByLabelText('Board view')).toBeInTheDocument();
    expect(screen.getByLabelText('List view')).toBeInTheDocument();
  });

  it('shows filter chips when phase filters are active', () => {
    renderFilterBar({ selectedPhases: ['build', 'test'] });
    expect(screen.getByLabelText('Remove build filter')).toBeInTheDocument();
    expect(screen.getByLabelText('Remove test filter')).toBeInTheDocument();
  });

  it('hides filter chips when no filters active', () => {
    const { container } = renderFilterBar();
    expect(container.querySelectorAll('[aria-label^="Remove"]').length).toBe(0);
  });
});
