import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MarkdownRenderer } from './MarkdownRenderer';
import type { ViewerTab } from '../../../types/viewer';

const tab: ViewerTab = {
  id: 'readme.md',
  label: 'readme.md',
  filePath: 'readme.md',
  fileType: 'markdown',
  projectId: 'proj-1',
};

describe('MarkdownRenderer', () => {
  it('renders markdown headings', () => {
    render(<MarkdownRenderer tab={tab} content="# Hello World" projectId="proj-1" />);
    expect(screen.getByText('Hello World')).toBeInTheDocument();
  });

  it('renders bold text', () => {
    render(<MarkdownRenderer tab={tab} content="This is **bold** text" projectId="proj-1" />);
    expect(screen.getByText('bold')).toBeInTheDocument();
  });

  it('renders GFM tables', () => {
    const md = '| A | B |\n|---|---|\n| 1 | 2 |';
    render(<MarkdownRenderer tab={tab} content={md} projectId="proj-1" />);
    expect(screen.getByText('A')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });
});
