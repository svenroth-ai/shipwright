import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PanelLayout } from './PanelLayout';

describe('PanelLayout', () => {
  it('renders both panels', () => {
    render(
      <PanelLayout
        leftPanel={<div>Left Content</div>}
        rightPanel={<div>Right Content</div>}
      />,
    );
    expect(screen.getByText('Left Content')).toBeInTheDocument();
    expect(screen.getByText('Right Content')).toBeInTheDocument();
  });

  it('renders drag handle', () => {
    render(
      <PanelLayout
        leftPanel={<div>Left</div>}
        rightPanel={<div>Right</div>}
      />,
    );
    expect(screen.getByRole('separator')).toBeInTheDocument();
  });
});
