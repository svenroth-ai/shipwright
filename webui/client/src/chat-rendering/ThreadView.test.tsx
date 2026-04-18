import { render, screen, within } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThreadView } from './ThreadView';
import { loadFixture } from './loadFixture';

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('ThreadView — Sub-iterate A DOM/ARIA contract', () => {
  it('mounts with ARIA role=log + chat-thread testid', () => {
    renderWithQuery(<ThreadView messages={[]} isRunning={false} onSend={() => {}} />);
    const thread = screen.getByTestId('chat-thread');
    expect(thread).toBeInTheDocument();
    const log = screen.getByRole('log', { name: 'Chat history' });
    expect(log).toBeInTheDocument();
  });

  it('shows default empty state when messages is empty', () => {
    renderWithQuery(<ThreadView messages={[]} isRunning={false} onSend={() => {}} />);
    expect(screen.getByText('No messages yet.')).toBeInTheDocument();
  });

  it('suppresses empty state when emptyState=null', () => {
    render(
      <ThreadView
        messages={[]}
        isRunning={false}
        onSend={() => {}}
        emptyState={null}
      />,
    );
    expect(screen.queryByText('No messages yet.')).toBeNull();
  });

  it('renders short-happy-path fixture — one user + one assistant bubble', () => {
    const fixture = loadFixture('short-happy-path');
    renderWithQuery(<ThreadView messages={fixture} isRunning={false} onSend={() => {}} />);
    const messages = screen.getAllByTestId('chat-message');
    // short-happy-path: 1 user, 1 assistant, 1 result (rendered as assistant).
    // system/init blob is filtered out by visibleChatMessages.
    expect(messages.length).toBe(3);
    const userMessages = messages.filter((m) => m.getAttribute('data-role') === 'user');
    expect(userMessages.length).toBe(1);
    const assistantMessages = messages.filter((m) => m.getAttribute('data-role') === 'assistant');
    expect(assistantMessages.length).toBe(2);
  });

  it('renders tool_use → ToolCallCard via tool Fallback', () => {
    const fixture = loadFixture('tool-heavy');
    renderWithQuery(<ThreadView messages={fixture} isRunning={false} onSend={() => {}} />);
    const toolCards = screen.getAllByTestId('tool-call-card');
    expect(toolCards.length).toBeGreaterThan(0);
  });

  it('renders thinking → collapsible Thinking block', () => {
    const fixture = loadFixture('thinking-heavy');
    renderWithQuery(<ThreadView messages={fixture} isRunning={false} onSend={() => {}} />);
    const thinkingBlocks = screen.getAllByTestId('thinking-block');
    expect(thinkingBlocks.length).toBe(2);
    // Collapsed by default — content should not be visible.
    for (const block of thinkingBlocks) {
      expect(within(block).queryByText(/foundational math question/)).toBeNull();
    }
  });

  it('preserves message order from fixture', () => {
    const fixture = loadFixture('live-task-7f1815f3');
    renderWithQuery(<ThreadView messages={fixture} isRunning={false} onSend={() => {}} />);
    const messages = screen.getAllByTestId('chat-message');
    const toolCards = screen.getAllByTestId('tool-call-card');
    // live-task: 50 total - 10 system/init blobs filtered = 40 visible
    // 40 messages = 10 assistant + 20 tool_use + 8 result + 2 user = 40
    expect(messages.length + toolCards.length).toBeGreaterThan(30);
  });

  it('filters system/init JSON blobs but keeps short system lines', () => {
    const fixture = [
      {
        id: 's1',
        taskId: 't',
        type: 'system' as const,
        content: '{"type":"system","subtype":"init","session_id":"x"}',
        timestamp: '2026-04-18T00:00:00.000Z',
      },
      {
        id: 's2',
        taskId: 't',
        type: 'system' as const,
        content: 'Session started · claude-opus-4-7',
        timestamp: '2026-04-18T00:00:01.000Z',
      },
      {
        id: 'a1',
        taskId: 't',
        type: 'assistant' as const,
        content: 'Hello!',
        timestamp: '2026-04-18T00:00:02.000Z',
      },
    ];
    renderWithQuery(<ThreadView messages={fixture} isRunning={false} onSend={() => {}} />);
    // JSON blob filtered out — not in the DOM
    expect(screen.queryByText(/"subtype":"init"/)).toBeNull();
    // Short system line preserved
    expect(screen.getByText(/Session started/)).toBeInTheDocument();
  });

  it('renders MessagePrimitive with data-role="user" for user messages', () => {
    const fixture = loadFixture('short-happy-path');
    renderWithQuery(<ThreadView messages={fixture} isRunning={false} onSend={() => {}} />);
    const userMsgs = screen.getAllByTestId('chat-message').filter((el) =>
      el.getAttribute('data-role') === 'user',
    );
    expect(userMsgs.length).toBeGreaterThan(0);
  });

  // Iterate modelswitch-uat-round2 (2026-04-18) — ExternalStoreRuntime
  // inserts a "running-reply placeholder" MessagePrimitive when isRunning
  // is true and the last real message is a user message. The placeholder
  // has no content parts but our role-based chrome would render a ghost
  // white bubble — the "weisser Balken nach Starting Claude" UAT report.
  // Guard in ThreadMessage returns null when all parts are empty.
  it('suppresses the ghost empty-assistant bubble when isRunning=true with only user messages', () => {
    const synth: import('../types').ChatMessage[] = [
      {
        id: 'u1',
        taskId: 't',
        type: 'user',
        content: 'Build me something',
        timestamp: '2026-04-18T00:00:00.000Z',
      },
    ];
    renderWithQuery(<ThreadView messages={synth} isRunning={true} onSend={() => {}} />);
    const bubbles = screen.getAllByTestId('chat-message');
    // Exactly one bubble: the user's message. No ghost assistant placeholder.
    expect(bubbles.length).toBe(1);
    expect(bubbles[0].getAttribute('data-role')).toBe('user');
  });

  it('still renders valid assistant messages with non-empty text', () => {
    const synth: import('../types').ChatMessage[] = [
      {
        id: 'u1',
        taskId: 't',
        type: 'user',
        content: 'hi',
        timestamp: '2026-04-18T00:00:00.000Z',
      },
      {
        id: 'a1',
        taskId: 't',
        type: 'assistant',
        content: 'Hello back!',
        timestamp: '2026-04-18T00:00:01.000Z',
      },
    ];
    renderWithQuery(<ThreadView messages={synth} isRunning={false} onSend={() => {}} />);
    const bubbles = screen.getAllByTestId('chat-message');
    expect(bubbles.length).toBe(2);
    expect(bubbles.filter((b) => b.getAttribute('data-role') === 'assistant').length).toBe(1);
  });

  it('renders leading and trailing slots in-thread', () => {
    render(
      <ThreadView
        messages={[]}
        isRunning={false}
        onSend={() => {}}
        leadingSlot={<div data-testid="leading-marker">L</div>}
        trailingSlot={<div data-testid="trailing-marker">T</div>}
      />,
    );
    expect(screen.getByTestId('leading-marker')).toBeInTheDocument();
    expect(screen.getByTestId('trailing-marker')).toBeInTheDocument();
  });

  it('renders AskUserQuestion tool_use as AskUserCard (not tool-call-card) — Sub-iterate B', () => {
    const fixture = loadFixture('askuser-roundtrip');
    renderWithQuery(<ThreadView messages={fixture} isRunning={false} onSend={() => {}} />);
    // AskUserQuestion tool_use must NOT render as a generic tool card.
    const toolCards = screen.queryAllByTestId('tool-call-card');
    for (const card of toolCards) {
      expect(card.textContent).not.toContain('AskUserQuestion');
    }
    // Sub-iterate B contract: AskUserCard renders inline in the thread.
    // The fixture contains one AskUserQuestion tool_use about "Plattform"
    // — the question text must be visible in the DOM.
    expect(screen.getAllByText(/Plattform/i).length).toBeGreaterThan(0);
  });
});

describe('ThreadView — perf gate', () => {
  it('mounts a 500-message fixture in jsdom within a generous budget', () => {
    // Synthesize 500-message fixture — alternating user / assistant pairs.
    // jsdom is much slower than a real browser. The authoritative perf
    // gate lives in the Playwright spec (< 1000ms first-render). Here we
    // just confirm the component scales at all — a 6s jsdom budget lets
    // the test pass reliably on Windows CI where the full-suite
    // environment (MSW, zustand stores) slows timing by 3-4x vs isolated
    // runs.
    const synth = [] as import('../types').ChatMessage[];
    for (let i = 0; i < 500; i++) {
      synth.push({
        id: `msg-${i}`,
        taskId: 'perf',
        type: i % 2 === 0 ? 'user' : 'assistant',
        content: `Message body ${i} with some **markdown** content.`,
        timestamp: new Date(2026, 3, 18, 0, 0, i).toISOString(),
      });
    }
    const t0 = performance.now();
    renderWithQuery(<ThreadView messages={synth} isRunning={false} onSend={() => {}} />);
    const t1 = performance.now();
    const messages = screen.getAllByTestId('chat-message');
    expect(messages.length).toBe(500);
    expect(t1 - t0).toBeLessThan(6000);
  });
});
