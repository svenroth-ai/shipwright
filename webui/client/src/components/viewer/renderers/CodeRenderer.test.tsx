import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CodeRenderer } from './CodeRenderer';
import type { ViewerTab } from '../../../types/viewer';

const tab: ViewerTab = {
  id: 'src/App.tsx',
  label: 'App.tsx',
  filePath: 'src/App.tsx',
  fileType: 'code',
  projectId: 'proj-1',
};

describe('CodeRenderer', () => {
  it('renders code with line numbers', () => {
    render(<CodeRenderer tab={tab} content={'const x = 1;\nconst y = 2;'} projectId="proj-1" />);
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByTestId('code-renderer')).toBeInTheDocument();
  });

  it('shows file name and language', () => {
    render(<CodeRenderer tab={tab} content="code" projectId="proj-1" />);
    expect(screen.getByText(/App.tsx — tsx/)).toBeInTheDocument();
  });
});
