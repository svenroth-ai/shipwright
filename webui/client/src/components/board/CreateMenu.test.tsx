import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { ReactNode } from 'react';
import { CreateMenu } from './CreateMenu';

// Radix DropdownMenu is awkward in JSDOM (pointer events, portals). Mock it
// to a flat passthrough so we can assert that the trigger renders and items
// wire to callbacks via `onSelect`.
vi.mock('@radix-ui/react-dropdown-menu', () => ({
  Root: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Trigger: ({ children }: { children: ReactNode; asChild?: boolean }) => <>{children}</>,
  Portal: ({ children }: { children: ReactNode }) => <>{children}</>,
  Content: ({ children }: { children: ReactNode }) => <div role="menu">{children}</div>,
  Item: ({ children, onSelect }: { children: ReactNode; onSelect?: () => void }) => (
    <button type="button" onClick={onSelect}>{children}</button>
  ),
}));

describe('CreateMenu', () => {
  it('renders the trigger button with "New" label', () => {
    render(<CreateMenu onNewTask={vi.fn()} onNewPipeline={vi.fn()} />);
    expect(screen.getByRole('button', { name: /create new/i })).toBeInTheDocument();
    expect(screen.getByText('New')).toBeInTheDocument();
  });

  it('renders both menu items', () => {
    render(<CreateMenu onNewTask={vi.fn()} onNewPipeline={vi.fn()} />);
    expect(screen.getByText('New Task')).toBeInTheDocument();
    expect(screen.getByText('New Pipeline…')).toBeInTheDocument();
  });

  it('calls onNewTask when "New Task" item is selected', () => {
    const onNewTask = vi.fn();
    const onNewPipeline = vi.fn();
    render(<CreateMenu onNewTask={onNewTask} onNewPipeline={onNewPipeline} />);
    fireEvent.click(screen.getByText('New Task'));
    expect(onNewTask).toHaveBeenCalledTimes(1);
    expect(onNewPipeline).not.toHaveBeenCalled();
  });

  it('calls onNewPipeline when "New Pipeline" item is selected', () => {
    const onNewTask = vi.fn();
    const onNewPipeline = vi.fn();
    render(<CreateMenu onNewTask={onNewTask} onNewPipeline={onNewPipeline} />);
    fireEvent.click(screen.getByText('New Pipeline…'));
    expect(onNewPipeline).toHaveBeenCalledTimes(1);
    expect(onNewTask).not.toHaveBeenCalled();
  });
});
