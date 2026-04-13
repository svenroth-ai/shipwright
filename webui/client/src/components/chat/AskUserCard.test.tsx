import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { AskUserCard } from './AskUserCard';
import type { ChatMessage } from '../../types';

vi.mock('../../hooks/useInbox', () => ({
  useAnswerInbox: () => ({ mutate: vi.fn(), isPending: false }),
}));

function renderCard(toolInput: unknown, content = '') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const message: ChatMessage = {
    id: 'ask-1',
    taskId: 't1',
    type: 'tool_use',
    content,
    toolName: 'AskUserQuestion',
    toolInput,
    timestamp: '2026-04-13T00:00:00Z',
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <AskUserCard message={message} />
    </QueryClientProvider>,
  );
}

describe('AskUserCard', () => {
  it('renders question text from the real Claude Code schema (questions[0].options direct)', () => {
    // Real shape verified from chat-history jsonl on 2026-04-13.
    renderCard({
      questions: [
        {
          question: 'How urgent is this?',
          header: 'Priority',
          options: [
            { label: 'High', description: 'Blocks release' },
            { label: 'Low' },
          ],
          multiSelect: false,
        },
      ],
    });
    expect(screen.getByText('How urgent is this?')).toBeInTheDocument();
    expect(screen.getByText('Priority')).toBeInTheDocument();
  });

  it('renders suggestion chips for each option label', () => {
    renderCard({
      questions: [
        {
          question: 'Pick one',
          options: [{ label: 'Alpha' }, { label: 'Bravo' }, { label: 'Charlie' }],
          multiSelect: false,
        },
      ],
    });
    expect(screen.getByRole('button', { name: 'Alpha' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Bravo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Charlie' })).toBeInTheDocument();
  });

  it('still renders a legacy flat-schema tool_input', () => {
    renderCard({ question: 'Continue?', options: ['Yes', 'No'] });
    expect(screen.getByText('Continue?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Yes' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'No' })).toBeInTheDocument();
  });

  it('shows a textarea with "Type your answer..." placeholder', () => {
    renderCard({ questions: [{ question: 'Free-text only' }] });
    expect(screen.getByPlaceholderText('Type your answer...')).toBeInTheDocument();
  });

  it('falls back to "Question from Claude" when tool_input is empty', () => {
    renderCard({});
    expect(screen.getByText('Question from Claude')).toBeInTheDocument();
  });

  it('Submit Answer button is disabled until the user picks an option or types text', () => {
    renderCard({ questions: [{ question: 'Anything?' }] });
    expect(screen.getByRole('button', { name: 'Submit Answer' })).toBeDisabled();
  });
});
