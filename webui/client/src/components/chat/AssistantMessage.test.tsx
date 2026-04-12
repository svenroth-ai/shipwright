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
  it('renders markdown content with Claude sender label', () => {
    render(<AssistantMessage message={msg} />);
    expect(screen.getByText('Claude')).toBeInTheDocument();
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('bold')).toBeInTheDocument();
  });

  it('renders avatar "C"', () => {
    render(<AssistantMessage message={msg} />);
    expect(screen.getByText('C')).toBeInTheDocument();
  });

  it('renders streaming content with indicator', () => {
    render(<AssistantMessage content="Thinking..." isStreaming />);
    expect(screen.getByText('Thinking...')).toBeInTheDocument();
  });
});
