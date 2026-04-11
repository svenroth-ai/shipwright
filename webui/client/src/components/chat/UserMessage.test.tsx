import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { UserMessage } from './UserMessage';
import type { ChatMessage } from '../../types';

const msg: ChatMessage = {
  id: 'msg-1',
  taskId: 'task-1',
  type: 'user',
  content: 'Hello world',
  timestamp: '2026-04-10T10:00:00Z',
};

describe('UserMessage', () => {
  it('renders message content', () => {
    render(<UserMessage message={msg} />);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });
});
