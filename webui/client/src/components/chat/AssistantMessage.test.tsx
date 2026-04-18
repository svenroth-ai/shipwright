import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { AssistantMessage } from './AssistantMessage';
import type { ChatMessage } from '../../types';

const msg: ChatMessage = {
  id: 'msg-2',
  taskId: 'task-1',
  type: 'assistant',
  content: '# Hello\n\nThis is **bold** text.\n\n```js\nconsole.log("hi");\n```',
  timestamp: '2026-04-10T10:00:01Z',
};

describe('AssistantMessage', () => {
  it('renders markdown content (headings, bold, code)', () => {
    render(<AssistantMessage message={msg} />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('bold')).toBeInTheDocument();
  });

  it('renders streaming content', () => {
    render(<AssistantMessage content="Thinking..." isStreaming />);
    expect(screen.getByText('Thinking...')).toBeInTheDocument();
  });

  it('renders markdown tables with proper cell separation', () => {
    const tableMsg: ChatMessage = {
      id: 't',
      taskId: 'task-1',
      type: 'assistant',
      content: '| Team | Points |\n|------|--------|\n| Bayern | 73 |\n| Dortmund | 64 |',
      timestamp: '2026-04-10T10:00:02Z',
    };
    render(<AssistantMessage message={tableMsg} />);
    // Each cell should be its own element — not concatenated
    expect(screen.getByText('Team')).toBeInTheDocument();
    expect(screen.getByText('Points')).toBeInTheDocument();
    expect(screen.getByText('Bayern')).toBeInTheDocument();
    expect(screen.getByText('73')).toBeInTheDocument();
  });
});
