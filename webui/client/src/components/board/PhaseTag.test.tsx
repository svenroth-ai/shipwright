import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PhaseTag } from './PhaseTag';

describe('PhaseTag', () => {
  it('renders nothing when phase is undefined', () => {
    const { container } = render(<PhaseTag />);
    expect(container.firstChild).toBeNull();
  });

  it.each([
    ['build', 'bg-orange-500'],
    ['test', 'bg-green-500'],
    ['deploy', 'bg-teal-500'],
    ['plan', 'bg-blue-500'],
    ['design', 'bg-purple-500'],
    ['project', 'bg-gray-400'],
  ])('renders %s phase with correct color class', (phase, expectedClass) => {
    render(<PhaseTag phase={phase} />);
    const tag = screen.getByText(phase);
    expect(tag.className).toContain(expectedClass);
  });

  it('falls back to gray for unknown phase', () => {
    render(<PhaseTag phase="unknown" />);
    const tag = screen.getByText('unknown');
    expect(tag.className).toContain('bg-gray-400');
  });
});
