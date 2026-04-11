import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { InboxBadge } from './InboxBadge';

describe('InboxBadge', () => {
  it('renders nothing when count is 0', () => {
    const { container } = render(<InboxBadge count={0} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows count for values 1-99', () => {
    render(<InboxBadge count={5} />);
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('shows 99+ when count exceeds 99', () => {
    render(<InboxBadge count={100} />);
    expect(screen.getByText('99+')).toBeInTheDocument();
  });

  it('shows exact count at boundary 99', () => {
    render(<InboxBadge count={99} />);
    expect(screen.getByText('99')).toBeInTheDocument();
  });
});
