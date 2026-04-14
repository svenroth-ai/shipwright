import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mergeCommitted } from './mergeCommitted';
import type { ChatMessage } from '../types';

function msg(id: string, timestamp: string, content = `content-${id}`): ChatMessage {
  return { id, taskId: 't1', type: 'assistant', content, timestamp };
}

describe('mergeCommitted', () => {
  it('returns a single-element array when prev is undefined', () => {
    const result = mergeCommitted(undefined, msg('a', '2026-04-14T10:00:00Z'));
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('a');
  });

  it('appends to the end when incoming has the latest timestamp', () => {
    const prev = [msg('a', '2026-04-14T10:00:00Z'), msg('b', '2026-04-14T10:01:00Z')];
    const result = mergeCommitted(prev, msg('c', '2026-04-14T10:02:00Z'));
    expect(result.map((m) => m.id)).toEqual(['a', 'b', 'c']);
  });

  it('inserts in the middle when timestamps are out of order', () => {
    const prev = [msg('a', '2026-04-14T10:00:00Z'), msg('c', '2026-04-14T10:02:00Z')];
    const result = mergeCommitted(prev, msg('b', '2026-04-14T10:01:00Z'));
    expect(result.map((m) => m.id)).toEqual(['a', 'b', 'c']);
  });

  it('prepends when incoming has the earliest timestamp', () => {
    const prev = [msg('b', '2026-04-14T10:01:00Z'), msg('c', '2026-04-14T10:02:00Z')];
    const result = mergeCommitted(prev, msg('a', '2026-04-14T10:00:00Z'));
    expect(result.map((m) => m.id)).toEqual(['a', 'b', 'c']);
  });

  it('preserves insertion order for equal timestamps (stable)', () => {
    const ts = '2026-04-14T10:00:00Z';
    let result: ChatMessage[] = [];
    result = mergeCommitted(result, msg('a', ts));
    result = mergeCommitted(result, msg('b', ts));
    result = mergeCommitted(result, msg('c', ts));
    expect(result.map((m) => m.id)).toEqual(['a', 'b', 'c']);
  });

  it('dedupes by id when the incoming id already exists', () => {
    const prev = [msg('a', '2026-04-14T10:00:00Z')];
    const result = mergeCommitted(prev, msg('a', '2026-04-14T10:00:00Z'));
    expect(result).toHaveLength(1);
  });

  it('replaces existing content when same id arrives with different content', () => {
    const prev = [msg('a', '2026-04-14T10:00:00Z', 'v1')];
    const result = mergeCommitted(prev, msg('a', '2026-04-14T10:00:00Z', 'v2'));
    expect(result).toHaveLength(1);
    expect(result[0].content).toBe('v2');
  });

  it('returns a new array instance (referential identity change)', () => {
    const prev = [msg('a', '2026-04-14T10:00:00Z')];
    const result = mergeCommitted(prev, msg('b', '2026-04-14T10:01:00Z'));
    expect(result).not.toBe(prev);
  });

  it('does not mutate prev', () => {
    const prev = [msg('a', '2026-04-14T10:00:00Z')];
    const snapshot = [...prev];
    mergeCommitted(prev, msg('b', '2026-04-14T10:01:00Z'));
    expect(prev).toEqual(snapshot);
  });

  it('handles dense sequences in monotonic order', () => {
    let result: ChatMessage[] = [];
    for (let i = 0; i < 12; i++) {
      result = mergeCommitted(result, msg(`m-${i}`, `2026-04-14T10:${String(i).padStart(2, '0')}:00Z`));
    }
    expect(result).toHaveLength(12);
    expect(result.map((m) => m.id)).toEqual(
      Array.from({ length: 12 }, (_, i) => `m-${i}`),
    );
  });

  it('handles an out-of-order dense sequence and still produces sorted output', () => {
    const ordered = Array.from({ length: 8 }, (_, i) => msg(`m-${i}`, `2026-04-14T10:${String(i).padStart(2, '0')}:00Z`));
    const shuffled = [ordered[3], ordered[0], ordered[6], ordered[1], ordered[7], ordered[2], ordered[5], ordered[4]];
    let result: ChatMessage[] = [];
    for (const m of shuffled) result = mergeCommitted(result, m);
    expect(result.map((m) => m.id)).toEqual(['m-0', 'm-1', 'm-2', 'm-3', 'm-4', 'm-5', 'm-6', 'm-7']);
  });
});

describe('mergeCommitted dev-only warning on same-id content diff', () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  afterEach(() => {
    warnSpy.mockRestore();
  });

  it('logs a warning when the same id arrives with different content in dev mode', () => {
    // vitest runs with import.meta.env.DEV=true by default
    const prev = [msg('a', '2026-04-14T10:00:00Z', 'original')];
    mergeCommitted(prev, msg('a', '2026-04-14T10:00:00Z', 'modified'));
    expect(warnSpy).toHaveBeenCalledOnce();
    const call = warnSpy.mock.calls[0];
    expect(call[0]).toContain('same-id content diff');
    expect(call[1]).toBe('a');
  });

  it('does not warn when same id arrives with identical content', () => {
    const prev = [msg('a', '2026-04-14T10:00:00Z', 'same')];
    mergeCommitted(prev, msg('a', '2026-04-14T10:00:00Z', 'same'));
    expect(warnSpy).not.toHaveBeenCalled();
  });
});
