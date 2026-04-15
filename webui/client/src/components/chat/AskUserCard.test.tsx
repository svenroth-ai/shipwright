import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AskUserCard } from './AskUserCard';
import { ChatAwaitingContext } from '../../contexts/ChatAwaitingContext';
import type { ChatMessage } from '../../types';

const answerMutateMock = vi.fn();
// Iterate 14.5 — mutable inbox-item stub so individual tests can control
// the `notBlocked` / `status` values returned by the `useInboxItem` hook.
let useInboxItemReturn: unknown = undefined;
vi.mock('../../hooks/useInbox', () => ({
  useAnswerInbox: () => ({ mutate: (args: unknown) => answerMutateMock(args), isPending: false }),
  useInboxItem: () => useInboxItemReturn,
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
    useInboxItemReturn = undefined;
  });

  it('submits the answer keyed on message.toolUseId, sending answers array (single part)', async () => {
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
    expect(answerMutateMock).toHaveBeenCalledWith({
      id: 'toolu_01HelloWorld',
      answers: [{ index: 0, answer: 'Alpha' }],
    });
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
    expect(answerMutateMock).toHaveBeenCalledWith({
      id: 'ask-1',
      answers: [{ index: 0, answer: 'Yes' }],
    });
  });

  it('renders question text from the real Claude Code schema (questions[0].options direct)', () => {
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
    // Single-part items still render their header (when present, even if
    // we don't show the "{N} questions" tag).
    // For single-part items we omit per-part headers but the question text
    // is enough to assert.
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
    expect(answerMutateMock).toHaveBeenCalledTimes(1);
  });

  // ──────────────────────────────────────────────────────────────────────
  // Iterate 14.2 — multi-question accordion rendering
  // ──────────────────────────────────────────────────────────────────────

  it('renders ALL parts as an accordion when Claude asks multiple questions', () => {
    renderCard({
      questions: [
        { question: 'What priority?', header: 'Priority', options: [{ label: 'High' }, { label: 'Low' }] },
        { question: 'Who owns this?', header: 'Owner' },
        { question: 'Estimate?', header: 'Estimate' },
      ],
    });
    expect(screen.getByText('What priority?')).toBeInTheDocument();
    expect(screen.getByText('Who owns this?')).toBeInTheDocument();
    expect(screen.getByText('Estimate?')).toBeInTheDocument();
    expect(screen.getByText('3 questions')).toBeInTheDocument();
  });

  it('Submit is disabled until EVERY part has an answer', async () => {
    renderCard({
      questions: [
        { question: 'Q1?', options: [{ label: 'A' }, { label: 'B' }] },
        { question: 'Q2?' },
      ],
    });
    const submit = screen.getByRole('button', { name: 'Submit Answer' });
    expect(submit).toBeDisabled();

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'A' }));
    expect(submit).toBeDisabled(); // Q2 still missing

    await user.type(screen.getByPlaceholderText('Type your answer...'), 'free text');
    expect(submit).not.toBeDisabled();
  });

  it('on Submit, sends answers array with one entry per part', async () => {
    renderCard(
      {
        questions: [
          { question: 'Q1?', options: [{ label: 'A' }] },
          { question: 'Q2?', options: [{ label: 'B' }] },
        ],
      },
      '',
      'toolu_multi',
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'A' }));
    await user.click(screen.getByRole('button', { name: 'B' }));
    await user.click(screen.getByRole('button', { name: 'Submit Answer' }));

    expect(answerMutateMock).toHaveBeenCalledWith({
      id: 'toolu_multi',
      answers: [
        { index: 0, answer: 'A' },
        { index: 1, answer: 'B' },
      ],
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // Iterate 14.5 — red flag warning banner
  // ──────────────────────────────────────────────────────────────────

  it('does NOT render the notBlocked banner when flag is absent', () => {
    useInboxItemReturn = {
      id: 'toolu_01',
      projectId: 'p1',
      taskId: 't1',
      parts: [{ question: 'Pick one' }],
      status: 'pending',
      createdAt: '2026-04-14T00:00:00Z',
    };
    renderCard(
      { questions: [{ question: 'Pick one', options: [{ label: 'Yes' }] }] },
      '',
      'toolu_01',
    );
    expect(screen.queryByTestId('ask-user-not-blocked-banner')).toBeNull();
  });

  it('renders the amber notBlocked banner when the persisted item has notBlocked=true', () => {
    useInboxItemReturn = {
      id: 'toolu_01',
      projectId: 'p1',
      taskId: 't1',
      parts: [{ question: 'Pick one' }],
      status: 'pending',
      createdAt: '2026-04-14T00:00:00Z',
      notBlocked: true,
    };
    renderCard(
      { questions: [{ question: 'Pick one', options: [{ label: 'Yes' }] }] },
      '',
      'toolu_01',
    );
    const banner = screen.getByTestId('ask-user-not-blocked-banner');
    expect(banner).toBeInTheDocument();
    expect(banner.textContent).toContain('Claude did not wait');
    expect(banner.textContent).toContain('tool_result');
  });

  it('notBlocked banner does NOT remove the Submit button', () => {
    useInboxItemReturn = {
      id: 'toolu_01',
      projectId: 'p1',
      taskId: 't1',
      parts: [{ question: 'Pick one' }],
      status: 'pending',
      createdAt: '2026-04-14T00:00:00Z',
      notBlocked: true,
    };
    renderCard(
      { questions: [{ question: 'Pick one', options: [{ label: 'Yes' }] }] },
      '',
      'toolu_01',
    );
    // Submit button stays — no ignore / answer-anyway alternatives.
    expect(screen.getByRole('button', { name: 'Submit Answer' })).toBeInTheDocument();
  });
});
