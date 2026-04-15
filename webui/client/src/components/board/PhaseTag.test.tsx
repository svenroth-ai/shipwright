import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PhaseTag } from './PhaseTag';

describe('PhaseTag', () => {
  it('renders nothing when phase is undefined', () => {
    const { container } = render(<PhaseTag />);
    expect(container.firstChild).toBeNull();
  });

  it.each([
    ['build', 'bg-orange-50', 'text-orange-700'],
    ['test', 'bg-green-100', 'text-green-700'],
    ['deploy', 'bg-cyan-100', 'text-cyan-700'],
    ['plan', 'bg-blue-100', 'text-blue-700'],
    ['design', 'bg-purple-100', 'text-purple-700'],
    ['project', 'bg-gray-100', 'text-gray-600'],
    ['iterate', 'bg-teal-100', 'text-teal-700'],
  ])('renders %s phase with correct color classes', (phase, expectedBg, expectedText) => {
    render(<PhaseTag phase={phase} />);
    const tag = screen.getByText(phase);
    expect(tag.className).toContain(expectedBg);
    expect(tag.className).toContain(expectedText);
  });

  it('falls back to gray for unknown phase', () => {
    render(<PhaseTag phase="unknown" />);
    const tag = screen.getByText('unknown');
    expect(tag.className).toContain('bg-gray-100');
    expect(tag.className).toContain('text-gray-600');
  });

  // Iterate 14.7.2 — monochrome mode for All-Projects view
  it('renders grey regardless of phase when monochrome is true', () => {
    render(<PhaseTag phase="build" monochrome />);
    const tag = screen.getByText('build');
    expect(tag.className).toContain('bg-gray-100');
    expect(tag.className).toContain('text-gray-700');
    expect(tag.className).not.toContain('bg-orange-50');
  });
});
