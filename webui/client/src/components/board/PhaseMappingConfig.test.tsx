import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { PhaseMappingConfig } from './PhaseMappingConfig';
import { DEFAULT_PHASE_MAPPING } from '../../lib/phaseMapping';

describe('PhaseMappingConfig', () => {
  it('renders all phase rows', () => {
    render(<PhaseMappingConfig mapping={DEFAULT_PHASE_MAPPING} onSave={vi.fn()} />);
    expect(screen.getByText('project')).toBeInTheDocument();
    expect(screen.getByText('build')).toBeInTheDocument();
    expect(screen.getByText('test')).toBeInTheDocument();
    expect(screen.getByText('deploy')).toBeInTheDocument();
  });

  it('calls onSave with modified mapping', async () => {
    const onSave = vi.fn();
    render(<PhaseMappingConfig mapping={DEFAULT_PHASE_MAPPING} onSave={onSave} />);

    const buildSelect = screen.getByTestId('mapping-build') as HTMLSelectElement;
    await userEvent.selectOptions(buildSelect, 'in_review');

    await userEvent.click(screen.getByText('Save'));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ build: 'in_review' }));
  });

  it('resets to defaults', async () => {
    const onSave = vi.fn();
    render(<PhaseMappingConfig mapping={{ ...DEFAULT_PHASE_MAPPING, build: 'done' }} onSave={onSave} />);

    await userEvent.click(screen.getByText('Reset to defaults'));
    await userEvent.click(screen.getByText('Save'));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ build: 'in_progress' }));
  });
});
