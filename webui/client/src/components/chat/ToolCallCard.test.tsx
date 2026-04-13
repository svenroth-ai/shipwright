import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import { ToolCallCard } from './ToolCallCard';
import type { ChatMessage } from '../../types';

const bashMsg: ChatMessage = {
  id: 'msg-3',
  taskId: 'task-1',
  type: 'tool_use',
  content: '',
  toolName: 'Bash',
  toolInput: { command: 'npm test' },
  toolOutput: 'All tests passed',
  timestamp: '2026-04-10T10:00:02Z',
};

const readMsg: ChatMessage = {
  id: 'msg-4',
  taskId: 'task-1',
  type: 'tool_use',
  content: '',
  toolName: 'Read',
  toolInput: { file_path: '/src/index.ts' },
  timestamp: '2026-04-10T10:00:03Z',
};

const errorResult: ChatMessage = {
  id: 'msg-5',
  taskId: 'task-1',
  type: 'tool_result',
  content: 'Error: file not found',
  isError: true,
  timestamp: '2026-04-10T10:00:04Z',
};

describe('ToolCallCard', () => {
  it('renders Bash tool title as "Run <command>"', () => {
    render(<ToolCallCard message={bashMsg} />);
    expect(screen.getByText('Run npm test')).toBeInTheDocument();
  });

  it('renders Read tool title with file path', () => {
    render(<ToolCallCard message={readMsg} />);
    expect(screen.getByText('Read /src/index.ts')).toBeInTheDocument();
  });

  it('is collapsed by default — output not visible', () => {
    render(<ToolCallCard message={bashMsg} />);
    expect(screen.queryByText('All tests passed')).not.toBeInTheDocument();
  });

  it('expands to show output on click', async () => {
    render(<ToolCallCard message={bashMsg} />);
    await userEvent.click(screen.getByText('Run npm test'));
    expect(screen.getByText('All tests passed')).toBeInTheDocument();
  });

  it('renders error badge for error tool_result', () => {
    render(<ToolCallCard message={errorResult} />);
    expect(screen.getByText('Error')).toBeInTheDocument();
  });

  it('shows error content when expanded', async () => {
    render(<ToolCallCard message={errorResult} />);
    await userEvent.click(screen.getByText('Tool'));
    expect(screen.getByText('Error: file not found')).toBeInTheDocument();
  });

  it('shows Done badge for a tool_use with toolOutput (folded result)', () => {
    render(<ToolCallCard message={bashMsg} />);
    expect(screen.getByText('Done')).toBeInTheDocument();
    expect(screen.queryByText('Running')).not.toBeInTheDocument();
  });

  it('shows Running badge for a tool_use still awaiting its result', () => {
    render(<ToolCallCard message={readMsg} />);
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.queryByText('Done')).not.toBeInTheDocument();
  });

  it('shows Error badge when tool_use has isError=true even without toolOutput', () => {
    const errorTool: ChatMessage = {
      id: 'msg-6',
      taskId: 'task-1',
      type: 'tool_use',
      content: '',
      toolName: 'Bash',
      toolInput: { command: 'false' },
      isError: true,
      toolOutput: 'command exited 1',
      timestamp: '2026-04-10T10:00:05Z',
    };
    render(<ToolCallCard message={errorTool} />);
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.queryByText('Running')).not.toBeInTheDocument();
  });

  it('shows Done for a legacy tool_result message (pre-fold compatibility)', () => {
    const legacyResult: ChatMessage = {
      id: 'msg-7',
      taskId: 'task-1',
      type: 'tool_result',
      content: 'ok',
      timestamp: '2026-04-10T10:00:06Z',
    };
    render(<ToolCallCard message={legacyResult} />);
    expect(screen.getByText('Done')).toBeInTheDocument();
  });
});
