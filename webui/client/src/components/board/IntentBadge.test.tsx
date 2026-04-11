import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { IntentBadge } from './IntentBadge';

describe('IntentBadge', () => {
  it('renders nothing when intent is undefined', () => {
    const { container } = render(<IntentBadge />);
    expect(container.firstChild).toBeNull();
  });

  it('renders fix badge with red styling', () => {
    render(<IntentBadge intent="fix" />);
    const badge = screen.getByText('fix');
    expect(badge.className).toContain('text-red-700');
  });

  it('renders feat badge with green styling', () => {
    render(<IntentBadge intent="feat" />);
    const badge = screen.getByText('feat');
    expect(badge.className).toContain('text-green-700');
  });

  it('renders chg badge with blue styling', () => {
    render(<IntentBadge intent="chg" />);
    const badge = screen.getByText('chg');
    expect(badge.className).toContain('text-blue-700');
  });
});
