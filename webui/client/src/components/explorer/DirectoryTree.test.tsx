import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { DirectoryTree } from './DirectoryTree';
import type { FileTreeNode } from '../../hooks/useFileTree';

const mockTree: FileTreeNode[] = [
  {
    name: 'src',
    path: 'src',
    type: 'directory',
    children: [
      { name: 'App.tsx', path: 'src/App.tsx', type: 'file', gitStatus: 'M' },
      { name: 'index.css', path: 'src/index.css', type: 'file' },
    ],
  },
  { name: 'README.md', path: 'README.md', type: 'file', gitStatus: 'A' },
];

describe('DirectoryTree', () => {
  it('renders nodes', () => {
    render(<DirectoryTree nodes={mockTree} onFileClick={vi.fn()} />);
    expect(screen.getByText('src')).toBeInTheDocument();
    expect(screen.getByText('README.md')).toBeInTheDocument();
  });

  it('calls onFileClick when file clicked', async () => {
    const onFileClick = vi.fn();
    render(<DirectoryTree nodes={mockTree} onFileClick={onFileClick} />);
    await userEvent.click(screen.getByText('README.md'));
    expect(onFileClick).toHaveBeenCalledWith('README.md');
  });

  it('shows git status badges', () => {
    render(<DirectoryTree nodes={mockTree} onFileClick={vi.fn()} />);
    expect(screen.getByText('A')).toBeInTheDocument();
  });
});
