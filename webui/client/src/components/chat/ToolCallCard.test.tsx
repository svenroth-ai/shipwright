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

describe('ToolCallCard', () => {
  it('renders collapsed by default with tool name', () => {
    render(<ToolCallCard message={bashMsg} />);
    expect(screen.getByText('Bash')).toBeInTheDocument();
    expect(screen.queryByText('All tests passed')).not.toBeInTheDocument();
  });

  it('expands to show output on click', async () => {
    render(<ToolCallCard message={bashMsg} />);
    await userEvent.click(screen.getByText('Bash'));
    expect(screen.getByText('All tests passed')).toBeInTheDocument();
  });
});
