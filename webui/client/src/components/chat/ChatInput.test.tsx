import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { ChatInput } from './ChatInput';

const PLACEHOLDER = 'Send a message or paste an image...';

function renderInput(props: Partial<React.ComponentProps<typeof ChatInput>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const defaults = { onSend: vi.fn(), isStreaming: false, autonomy: 'guided' as const, ...props };
  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <ChatInput {...defaults} />
      </QueryClientProvider>,
    ),
    onSend: defaults.onSend,
  };
}

describe('ChatInput', () => {
  it('sends message on Enter as ChatSendPayload', async () => {
    const { onSend } = renderInput();
    const textarea = screen.getByPlaceholderText(PLACEHOLDER);
    await userEvent.type(textarea, 'hello{enter}');
    expect(onSend).toHaveBeenCalledWith(expect.objectContaining({ message: 'hello' }));
  });

  it('does not send empty message', async () => {
    const { onSend } = renderInput();
    const textarea = screen.getByPlaceholderText(PLACEHOLDER);
    await userEvent.click(textarea);
    await userEvent.keyboard('{enter}');
    expect(onSend).not.toHaveBeenCalled();
  });

  it('inserts newline on Shift+Enter', async () => {
    renderInput();
    const textarea = screen.getByPlaceholderText(PLACEHOLDER) as HTMLTextAreaElement;
    await userEvent.type(textarea, 'line1{shift>}{enter}{/shift}line2');
    expect(textarea.value).toContain('line1');
    expect(textarea.value).toContain('line2');
  });

  it('renders paperclip attach button', () => {
    renderInput();
    const attachBtn = screen.getByTitle(/Attach image/i);
    expect(attachBtn).toBeInTheDocument();
  });
});
