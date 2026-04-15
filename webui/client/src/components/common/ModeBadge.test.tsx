import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ModeBadge } from './ModeBadge';

/**
 * Iterate 14.7.1 — ModeBadge pins the three known project modes to distinct
 * labels and color classes, and degrades cleanly when `mode` is missing.
 */

describe('ModeBadge', () => {
  it('renders the pipeline label with blue classes', () => {
    render(<ModeBadge mode="pipeline" />);
    const el = screen.getByTestId('mode-badge-pipeline');
    expect(el.textContent).toBe('Pipeline');
    expect(el.className).toMatch(/bg-blue-100/);
    expect(el.className).toMatch(/text-blue-900/);
  });

  it('renders the iterate label with amber classes', () => {
    render(<ModeBadge mode="iterate" />);
    const el = screen.getByTestId('mode-badge-iterate');
    expect(el.textContent).toBe('Iterate');
    expect(el.className).toMatch(/bg-amber-100/);
    expect(el.className).toMatch(/text-amber-900/);
  });

  it('renders the standalone label with gray classes', () => {
    render(<ModeBadge mode="standalone" />);
    const el = screen.getByTestId('mode-badge-standalone');
    expect(el.textContent).toBe('Standalone');
    expect(el.className).toMatch(/bg-gray-100/);
  });

  it('renders nothing when mode is undefined', () => {
    const { container } = render(<ModeBadge mode={undefined} />);
    expect(container.firstChild).toBeNull();
  });
});
