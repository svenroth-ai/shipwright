import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { PhaseFilter } from './PhaseFilter';
import { PIPELINE_PHASES } from '../../lib/phaseMapping';

function renderPhaseFilter(overrides = {}) {
  const defaults = {
    selectedPhases: [] as string[],
    onToggle: vi.fn(),
    onClear: vi.fn(),
    ...overrides,
  };
  return { ...render(<PhaseFilter {...defaults} />), ...defaults };
}

describe('PhaseFilter', () => {
  it('renders the correct number of phase checkboxes matching PIPELINE_PHASES', async () => {
    renderPhaseFilter();
    // Open the popover
    await userEvent.click(screen.getByText('Phase'));
    // Each pipeline phase should have a checkbox
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(PIPELINE_PHASES.length);
  });

  it('renders labels for all PIPELINE_PHASES', async () => {
    renderPhaseFilter();
    await userEvent.click(screen.getByText('Phase'));
    for (const phase of PIPELINE_PHASES) {
      expect(screen.getByText(phase)).toBeInTheDocument();
    }
  });

  it('does not include iterate as a phase', async () => {
    renderPhaseFilter();
    await userEvent.click(screen.getByText('Phase'));
    expect(screen.queryByText('iterate')).not.toBeInTheDocument();
  });

  it('includes security, compliance, and changelog phases', async () => {
    renderPhaseFilter();
    await userEvent.click(screen.getByText('Phase'));
    expect(screen.getByText('security')).toBeInTheDocument();
    expect(screen.getByText('compliance')).toBeInTheDocument();
    expect(screen.getByText('changelog')).toBeInTheDocument();
  });

  it('shows selected count badge when phases are active', () => {
    renderPhaseFilter({ selectedPhases: ['build', 'test'] });
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('shows Clear all button when filters are active', async () => {
    renderPhaseFilter({ selectedPhases: ['build'] });
    await userEvent.click(screen.getByText('Phase'));
    expect(screen.getByText('Clear all')).toBeInTheDocument();
  });
});
