import { describe, it, expect } from 'vitest';
import { foldToolResults } from './foldToolResults';
import type { ChatMessage } from '../types';

function msg(partial: Partial<ChatMessage> & { id: string; type: ChatMessage['type'] }): ChatMessage {
  return {
    taskId: 't1',
    content: '',
    timestamp: '2026-01-01T00:00:00Z',
    ...partial,
  };
}

describe('foldToolResults', () => {
  it('passes through non-tool messages unchanged', () => {
    const input: ChatMessage[] = [
      msg({ id: 'a', type: 'assistant', content: 'hello' }),
      msg({ id: 'b', type: 'thinking', content: 'hmm' }),
    ];
    const out = foldToolResults(input);
    expect(out).toHaveLength(2);
    expect(out[0].id).toBe('a');
    expect(out[1].id).toBe('b');
  });

  it('folds a matching tool_result into its tool_use by toolUseId', () => {
    const input: ChatMessage[] = [
      msg({ id: 'u1', type: 'tool_use', toolName: 'Read', toolInput: { file_path: '/a.txt' }, toolUseId: 'toolu_1' }),
      msg({ id: 'r1', type: 'tool_result', content: 'file contents', toolUseId: 'toolu_1' }),
    ];
    const out = foldToolResults(input);
    expect(out).toHaveLength(1);
    expect(out[0].type).toBe('tool_use');
    expect(out[0].toolName).toBe('Read');
    expect(out[0].toolOutput).toBe('file contents');
    expect(out[0].isError).toBeFalsy();
  });

  it('propagates isError from tool_result onto the folded tool_use', () => {
    const input: ChatMessage[] = [
      msg({ id: 'u1', type: 'tool_use', toolName: 'Bash', toolUseId: 'toolu_2' }),
      msg({ id: 'r1', type: 'tool_result', content: 'command failed', isError: true, toolUseId: 'toolu_2' }),
    ];
    const out = foldToolResults(input);
    expect(out).toHaveLength(1);
    expect(out[0].isError).toBe(true);
    expect(out[0].toolOutput).toBe('command failed');
  });

  it('keeps orphan tool_result (no matching tool_use) as a standalone entry', () => {
    const input: ChatMessage[] = [
      msg({ id: 'r1', type: 'tool_result', content: 'orphaned', toolUseId: 'toolu_ghost' }),
    ];
    const out = foldToolResults(input);
    expect(out).toHaveLength(1);
    expect(out[0].type).toBe('tool_result');
  });

  it('folds multiple interleaved tool_use / tool_result pairs', () => {
    const input: ChatMessage[] = [
      msg({ id: 'u1', type: 'tool_use', toolName: 'Read', toolUseId: 'toolu_1' }),
      msg({ id: 'u2', type: 'tool_use', toolName: 'Glob', toolUseId: 'toolu_2' }),
      msg({ id: 'r1', type: 'tool_result', content: 'A', toolUseId: 'toolu_1' }),
      msg({ id: 'a1', type: 'assistant', content: 'interleaved' }),
      msg({ id: 'r2', type: 'tool_result', content: 'B', toolUseId: 'toolu_2' }),
    ];
    const out = foldToolResults(input);
    // 2 tool_use (folded) + 1 assistant = 3 entries
    expect(out).toHaveLength(3);
    expect(out[0].toolName).toBe('Read');
    expect(out[0].toolOutput).toBe('A');
    expect(out[1].toolName).toBe('Glob');
    expect(out[1].toolOutput).toBe('B');
    expect(out[2].type).toBe('assistant');
  });

  it('leaves a tool_use without a matching tool_result as still "running" (no toolOutput set)', () => {
    const input: ChatMessage[] = [
      msg({ id: 'u1', type: 'tool_use', toolName: 'Bash', toolUseId: 'toolu_pending' }),
    ];
    const out = foldToolResults(input);
    expect(out).toHaveLength(1);
    expect(out[0].type).toBe('tool_use');
    expect(out[0].toolOutput).toBeUndefined();
    expect(out[0].isError).toBeFalsy();
  });

  it('tolerates tool_use without toolUseId (legacy messages) — passes through unchanged', () => {
    const input: ChatMessage[] = [
      msg({ id: 'u1', type: 'tool_use', toolName: 'Read' }),
      msg({ id: 'r1', type: 'tool_result', content: 'nothing to fold into' }),
    ];
    const out = foldToolResults(input);
    // No toolUseId on either side → both stay standalone
    expect(out).toHaveLength(2);
  });
});
