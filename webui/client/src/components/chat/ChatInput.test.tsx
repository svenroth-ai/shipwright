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

  // Iterate 14.8.3 — Send/Stop toggle
  it('renders Send button when not streaming', () => {
    renderInput({ isStreaming: false });
    expect(screen.getByTestId('send-button')).toBeInTheDocument();
    expect(screen.queryByTestId('stop-button')).toBeNull();
  });

  it('renders Stop button when streaming and onInterrupt is provided', () => {
    const onInterrupt = vi.fn();
    renderInput({ isStreaming: true, onInterrupt });
    expect(screen.getByTestId('stop-button')).toBeInTheDocument();
    expect(screen.queryByTestId('send-button')).toBeNull();
  });

  it('renders Send button (disabled) when streaming but no onInterrupt', () => {
    renderInput({ isStreaming: true });
    // Without onInterrupt, the send button renders (disabled)
    expect(screen.getByTestId('send-button')).toBeInTheDocument();
    expect(screen.queryByTestId('stop-button')).toBeNull();
  });

  it('click Stop calls onInterrupt', async () => {
    const onInterrupt = vi.fn();
    renderInput({ isStreaming: true, onInterrupt });
    await userEvent.click(screen.getByTestId('stop-button'));
    expect(onInterrupt).toHaveBeenCalledTimes(1);
  });

  it('Enter key during streaming does NOT call onInterrupt', async () => {
    const onInterrupt = vi.fn();
    renderInput({ isStreaming: true, onInterrupt });
    const textarea = screen.getByPlaceholderText(PLACEHOLDER);
    await userEvent.type(textarea, 'test{enter}');
    expect(onInterrupt).not.toHaveBeenCalled();
  });

  // Iterate 14.9 (Bug F2): when taskStatus is terminal/non-runnable,
  // the Stop button is suppressed even if isStreaming is still true.
  it('renders Send (not Stop) when task is orphaned even if isStreaming=true', () => {
    const onInterrupt = vi.fn();
    renderInput({ isStreaming: true, onInterrupt, taskStatus: 'orphaned' });
    expect(screen.getByTestId('send-button')).toBeInTheDocument();
    expect(screen.queryByTestId('stop-button')).toBeNull();
  });

  it('renders Send (not Stop) when task is done even if isStreaming=true', () => {
    const onInterrupt = vi.fn();
    renderInput({ isStreaming: true, onInterrupt, taskStatus: 'done' });
    expect(screen.getByTestId('send-button')).toBeInTheDocument();
    expect(screen.queryByTestId('stop-button')).toBeNull();
  });

  it('renders Stop when task is running and isStreaming=true', () => {
    const onInterrupt = vi.fn();
    renderInput({ isStreaming: true, onInterrupt, taskStatus: 'running' });
    expect(screen.getByTestId('stop-button')).toBeInTheDocument();
    expect(screen.queryByTestId('send-button')).toBeNull();
  });

  it('treats undefined taskStatus as runnable (back-compat)', () => {
    const onInterrupt = vi.fn();
    renderInput({ isStreaming: true, onInterrupt, taskStatus: undefined });
    // Without taskStatus, fall back to isStreaming-only behaviour.
    expect(screen.getByTestId('stop-button')).toBeInTheDocument();
  });

  // Iterate 14.13 — awaitingInit (spawn window) suppresses Send and
  // swaps the textarea placeholder. Distinct from isStreaming: nothing
  // is live yet so Stop is NOT shown.
  it('disables Send and changes placeholder when awaitingInit=true', () => {
    renderInput({ awaitingInit: true });
    const sendBtn = screen.getByTestId('send-button');
    expect(sendBtn).toBeDisabled();
    expect(screen.getByPlaceholderText('Waiting for Claude…')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(PLACEHOLDER)).toBeNull();
  });

  it('disables the textarea itself when awaitingInit=true', () => {
    renderInput({ awaitingInit: true });
    expect(screen.getByPlaceholderText('Waiting for Claude…')).toBeDisabled();
  });

  it('Enter key during awaitingInit does NOT call onSend', async () => {
    const onSend = vi.fn();
    renderInput({ onSend, awaitingInit: true });
    const textarea = screen.getByPlaceholderText('Waiting for Claude…');
    // Disabled textareas don't accept input via userEvent.type, so simulate
    // a keydown directly to confirm the handler short-circuits.
    await userEvent.click(textarea);
    await userEvent.keyboard('{enter}');
    expect(onSend).not.toHaveBeenCalled();
  });

  it('does NOT show Stop during awaitingInit (nothing live to interrupt)', () => {
    const onInterrupt = vi.fn();
    renderInput({ awaitingInit: true, onInterrupt });
    expect(screen.queryByTestId('stop-button')).toBeNull();
    expect(screen.getByTestId('send-button')).toBeInTheDocument();
  });
});
