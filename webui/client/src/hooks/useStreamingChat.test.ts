import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStreamingChat } from './useStreamingChat';
import type { NdjsonMessage } from '../types';

function assistantWithText(text: string): NdjsonMessage {
  return {
    type: 'assistant',
    message: {
      model: 'claude-opus-4-5',
      type: 'message',
      role: 'assistant',
      content: [{ type: 'text', text }],
    },
  } as NdjsonMessage;
}

describe('useStreamingChat', () => {
  it('displayContent only reflects the CURRENT assistant event, not a concat of all events in the stream', () => {
    // Regression: iterate-5 shipped a bug where appendToken accumulated text
    // across every assistant event in the same stream, producing a big blob
    // at the bottom of the chat that was "text1 + text2 + text3" from three
    // separate assistant turns. Fix: each assistant event resets displayContent.
    const { result } = renderHook(() => useStreamingChat());

    act(() => {
      result.current.startStream();
    });

    act(() => {
      result.current.processNdjsonMessage('t1', assistantWithText('Erste Antwort'));
    });
    expect(result.current.displayContent).toBe('Erste Antwort');

    act(() => {
      result.current.processNdjsonMessage('t1', assistantWithText('Zweite Antwort'));
    });
    // Must NOT be 'Erste AntwortZweite Antwort' — only the current turn.
    expect(result.current.displayContent).toBe('Zweite Antwort');

    act(() => {
      result.current.processNdjsonMessage('t1', assistantWithText('Dritte Antwort'));
    });
    expect(result.current.displayContent).toBe('Dritte Antwort');
  });

  it('multi-block assistant event concatenates its own text blocks but resets between events', () => {
    const { result } = renderHook(() => useStreamingChat());
    act(() => result.current.startStream());

    // One event with two text blocks → both concatenated within the event.
    const twoBlocks: NdjsonMessage = {
      type: 'assistant',
      message: {
        content: [
          { type: 'text', text: 'Hello ' },
          { type: 'text', text: 'world' },
        ],
      },
    } as NdjsonMessage;

    act(() => result.current.processNdjsonMessage('t1', twoBlocks));
    expect(result.current.displayContent).toBe('Hello world');

    // Next event resets.
    act(() => result.current.processNdjsonMessage('t1', assistantWithText('Neue Antwort')));
    expect(result.current.displayContent).toBe('Neue Antwort');
  });

  it('startStream resets all streaming state', () => {
    const { result } = renderHook(() => useStreamingChat());
    act(() => result.current.startStream());
    act(() => result.current.processNdjsonMessage('t1', assistantWithText('carry over')));
    expect(result.current.displayContent).toBe('carry over');

    act(() => result.current.startStream());
    expect(result.current.displayContent).toBe('');
    expect(result.current.streamingMessages).toEqual([]);
  });
});
