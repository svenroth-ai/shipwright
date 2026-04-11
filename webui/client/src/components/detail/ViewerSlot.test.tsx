import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ViewerSlot } from './ViewerSlot';

describe('ViewerSlot', () => {
  it('shows placeholder when no tabs open', () => {
    render(<ViewerSlot />);
    expect(screen.getByText('Select a file to view here')).toBeInTheDocument();
  });

  it('has viewer-slot test id', () => {
    render(<ViewerSlot />);
    expect(screen.getByTestId('viewer-slot')).toBeInTheDocument();
  });
});
