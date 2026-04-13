import { describe, it, expect } from 'vitest';
import { dedupeStreamingMessages } from './dedupeStreamingMessages';
import type { ChatMessage } from '../types';

function m(partial: Partial<ChatMessage> & { id: string; type: ChatMessage['type'] }): ChatMessage {
  return {
    taskId: 't1',
    content: '',
    timestamp: '2026-01-01T00:00:00Z',
    ...partial,
  };
}

describe('dedupeStreamingMessages', () => {
  it('returns streaming messages as-is when persisted list is empty', () => {
    const streaming: ChatMessage[] = [
      m({ id: 's1', type: 'tool_use', toolName: 'Read', toolUseId: 'toolu_1' }),
    ];
    expect(dedupeStreamingMessages([], streaming)).toEqual(streaming);
  });

  it('drops a streaming tool_use whose toolUseId already exists in persisted', () => {
    const persisted: ChatMessage[] = [
      m({ id: 'p1', type: 'tool_use', toolName: 'Read', toolUseId: 'toolu_1' }),
    ];
    const streaming: ChatMessage[] = [
      m({ id: 's1', type: 'tool_use', toolName: 'Read', toolUseId: 'toolu_1' }),
      m({ id: 's2', type: 'tool_use', toolName: 'Glob', toolUseId: 'toolu_2' }),
    ];
    const out = dedupeStreamingMessages(persisted, streaming);
    expect(out).toHaveLength(1);
    expect(out[0].toolUseId).toBe('toolu_2');
  });

  it('drops a streaming tool_result whose toolUseId already exists in persisted', () => {
    const persisted: ChatMessage[] = [
      m({ id: 'p1', type: 'tool_result', content: 'done', toolUseId: 'toolu_1' }),
    ];
    const streaming: ChatMessage[] = [
      m({ id: 's1', type: 'tool_result', content: 'done', toolUseId: 'toolu_1' }),
    ];
    expect(dedupeStreamingMessages(persisted, streaming)).toEqual([]);
  });

  it('drops a streaming assistant text already in persisted (by type+content prefix)', () => {
    const persisted: ChatMessage[] = [
      m({ id: 'p1', type: 'assistant', content: 'Hello there, starting analysis' }),
    ];
    const streaming: ChatMessage[] = [
      m({ id: 's1', type: 'assistant', content: 'Hello there, starting analysis' }),
      m({ id: 's2', type: 'assistant', content: 'And here is the next chunk' }),
    ];
    const out = dedupeStreamingMessages(persisted, streaming);
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('s2');
  });

  it('keeps a streaming tool_use without toolUseId (legacy) untouched', () => {
    const persisted: ChatMessage[] = [];
    const streaming: ChatMessage[] = [
      m({ id: 's1', type: 'tool_use', toolName: 'Read' }),
    ];
    expect(dedupeStreamingMessages(persisted, streaming)).toEqual(streaming);
  });

  it('does not remove distinct streaming messages when none match persisted', () => {
    const persisted: ChatMessage[] = [
      m({ id: 'p1', type: 'assistant', content: 'old reply' }),
    ];
    const streaming: ChatMessage[] = [
      m({ id: 's1', type: 'tool_use', toolName: 'Read', toolUseId: 'toolu_1' }),
      m({ id: 's2', type: 'assistant', content: 'fresh text' }),
    ];
    expect(dedupeStreamingMessages(persisted, streaming)).toHaveLength(2);
  });
});
