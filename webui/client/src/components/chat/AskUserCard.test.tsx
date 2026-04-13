import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AskUserCard } from './AskUserCard';
import { ChatAwaitingContext } from '../../contexts/ChatAwaitingContext';
import type { ChatMessage } from '../../types';

const answerMutateMock = vi.fn();
vi.mock('../../hooks/useInbox', () => ({
  useAnswerInbox: () => ({ mutate: (args: unknown) => answerMutateMock(args), isPending: false }),
  useInboxItem: () => undefined,
}));

function renderCard(
  toolInput: unknown,
  content = '',
  toolUseId?: string,
  awaitingValue?: { triggerAwaiting: () => void },
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const message: ChatMessage = {
    id: 'ask-1',
    taskId: 't1',
    type: 'tool_use',
    content,
    toolName: 'AskUserQuestion',
    toolInput,
    toolUseId,
    timestamp: '2026-04-13T00:00:00Z',
  };
  const card = <AskUserCard message={message} />;
  return render(
    <QueryClientProvider client={queryClient}>
      {awaitingValue ? (
        <ChatAwaitingContext.Provider value={awaitingValue}>{card}</ChatAwaitingContext.Provider>
      ) : (
        card
      )}
    </QueryClientProvider>,
  );
}

describe('AskUserCard', () => {
  beforeEach(() => {
    answerMutateMock.mockReset();
  });

  it('submits the answer keyed on message.toolUseId when present', async () => {
    renderCard(
      {
        questions: [
          {
            question: 'Pick one',
            options: [{ label: 'Alpha' }, { label: 'Bravo' }],
            multiSelect: false,
          },
        ],
      },
      '',
      'toolu_01HelloWorld',
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Alpha' }));
    await user.click(screen.getByRole('button', { name: 'Submit Answer' }));
    expect(answerMutateMock).toHaveBeenCalledWith({ id: 'toolu_01HelloWorld', answer: 'Alpha' });
  });

  it('falls back to message.id as inbox id when toolUseId is missing (legacy)', async () => {
    renderCard(
      { questions: [{ question: 'Legacy?', options: [{ label: 'Yes' }], multiSelect: false }] },
      '',
      undefined,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Yes' }));
    await user.click(screen.getByRole('button', { name: 'Submit Answer' }));
    expect(answerMutateMock).toHaveBeenCalledWith({ id: 'ask-1', answer: 'Yes' });
  });

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

  // Iterate 7 — inbox-answer latency fix
  it('calls ChatAwaitingContext.triggerAwaiting before submitting the answer', async () => {
    const triggerAwaiting = vi.fn();
    renderCard(
      { questions: [{ question: 'Pick', options: [{ label: 'Yes' }], multiSelect: false }] },
      '',
      'toolu_01Latency',
      { triggerAwaiting },
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Yes' }));
    await user.click(screen.getByRole('button', { name: 'Submit Answer' }));

    expect(triggerAwaiting).toHaveBeenCalledTimes(1);
    // Must have fired before (or at least alongside) the answer mutation —
    // otherwise the "Thinking…" indicator would still lag.
    expect(answerMutateMock).toHaveBeenCalledTimes(1);
  });
});
