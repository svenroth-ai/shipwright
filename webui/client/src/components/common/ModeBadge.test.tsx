import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ModeBadge } from './ModeBadge';

/**
 * Iterate 14.8.1 — ModeBadge is now inline-flex (no absolute/rotate).
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

  it('uses inline-flex layout, not absolute positioning', () => {
    render(<ModeBadge mode="pipeline" />);
    const el = screen.getByTestId('mode-badge-pipeline');
    expect(el.className).toMatch(/inline-flex/);
    expect(el.className).not.toMatch(/absolute/);
    expect(el.className).not.toMatch(/rotate-\[12deg\]/);
  });
});
