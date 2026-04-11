import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { JsonTreeRenderer } from './JsonTreeRenderer';
import type { ViewerTab } from '../../../types/viewer';

const tab: ViewerTab = {
  id: 'data.json',
  label: 'data.json',
  filePath: 'data.json',
  fileType: 'json',
  projectId: 'proj-1',
};

describe('JsonTreeRenderer', () => {
  it('renders JSON tree for valid content', () => {
    render(<JsonTreeRenderer tab={tab} content='{"name": "test", "count": 42}' projectId="proj-1" />);
    expect(screen.getByTestId('json-tree')).toBeInTheDocument();
    expect(screen.getByText('"test"')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('shows error for invalid JSON', () => {
    render(<JsonTreeRenderer tab={tab} content="not valid json" projectId="proj-1" />);
    expect(screen.getByText(/JSON parse error/)).toBeInTheDocument();
  });
});
