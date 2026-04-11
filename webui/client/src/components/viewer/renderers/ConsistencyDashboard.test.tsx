import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ConsistencyDashboard } from './ConsistencyDashboard';
import type { ViewerTab } from '../../../types/viewer';

const tab: ViewerTab = {
  id: 'report.json',
  label: 'report.json',
  filePath: 'report_consistency_report.json',
  fileType: 'consistency',
  projectId: 'proj-1',
};

describe('ConsistencyDashboard', () => {
  it('renders table with categories', () => {
    const content = JSON.stringify({
      categories: [
        { category: 'Naming', status: 'pass', details: 'All good' },
        { category: 'Types', status: 'fail', details: 'Missing types' },
      ],
    });
    render(<ConsistencyDashboard tab={tab} content={content} projectId="proj-1" />);
    expect(screen.getByTestId('consistency-dashboard')).toBeInTheDocument();
    expect(screen.getByText('Naming')).toBeInTheDocument();
    expect(screen.getByText('pass')).toBeInTheDocument();
    expect(screen.getByText('fail')).toBeInTheDocument();
  });

  it('shows empty state for invalid content', () => {
    render(<ConsistencyDashboard tab={tab} content="invalid" projectId="proj-1" />);
    expect(screen.getByText('No consistency data found')).toBeInTheDocument();
  });
});
