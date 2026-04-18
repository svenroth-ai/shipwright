import { describe, expect, it } from 'vitest';
import type { ThreadMessageLike } from '@assistant-ui/react';
import {
  convertToThreadMessage,
  isSystemInitBlob,
  visibleChatMessages,
} from './convertToThreadMessage';
import { listFixtureNames, loadFixture } from './loadFixture';
import type { ChatMessage } from '../types';

/**
 * Converter contract tests. Every sub-iterate must keep this suite green.
 * These assertions enumerate the semantic promises the converter makes —
 * breaking any of them is a breaking change and needs an explicit
 * ADR.
 */

describe('convertToThreadMessage', () => {
  describe('role mapping', () => {
    it('user → role:user, single text part', () => {
      const out = convertToThreadMessage({
        id: 'u1',
        taskId: 't',
        type: 'user',
        content: 'hello',
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      expect(out.role).toBe('user');
      expect(out.content).toEqual([{ type: 'text', text: 'hello' }]);
      expect(out.id).toBe('u1');
      expect(out.createdAt).toBeInstanceOf(Date);
    });

    it('assistant → role:assistant, single text part', () => {
      const out = convertToThreadMessage({
        id: 'a1',
        taskId: 't',
        type: 'assistant',
        content: 'sure',
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      expect(out.role).toBe('assistant');
      expect(out.content).toEqual([{ type: 'text', text: 'sure' }]);
    });

    it('result → role:assistant (rendered inline as final summary)', () => {
      const out = convertToThreadMessage({
        id: 'r1',
        taskId: 't',
        type: 'result',
        content: 'done.',
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      expect(out.role).toBe('assistant');
    });

    it('system → role:system', () => {
      const out = convertToThreadMessage({
        id: 's1',
        taskId: 't',
        type: 'system',
        content: 'Session started · claude-opus-4-7',
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      expect(out.role).toBe('system');
    });

    it('unknown type falls back to assistant/text', () => {
      const out = convertToThreadMessage({
        id: 'x1',
        taskId: 't',
        // @ts-expect-error — exercising defensive branch
        type: 'unknown-future-type',
        content: 'payload',
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      expect(out.role).toBe('assistant');
      expect(out.content).toEqual([{ type: 'text', text: 'payload' }]);
    });
  });

  describe('thinking → reasoning part', () => {
    it('maps thinking content to a reasoning part', () => {
      const out = convertToThreadMessage({
        id: 'th1',
        taskId: 't',
        type: 'thinking',
        content: 'let me consider...',
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      expect(out.role).toBe('assistant');
      expect(out.content).toEqual([{ type: 'reasoning', text: 'let me consider...' }]);
    });
  });

  describe('tool_use → tool-call part', () => {
    it('preserves toolUseId, toolName, toolInput', () => {
      const out = convertToThreadMessage({
        id: 'tu1',
        taskId: 't',
        type: 'tool_use',
        content: '',
        toolName: 'Bash',
        toolUseId: 'toolu_ABC',
        toolInput: { cmd: 'ls' },
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      const part = out.content[0] as {
        type: string;
        toolCallId: string;
        toolName: string;
        args: Record<string, unknown>;
      };
      expect(part.type).toBe('tool-call');
      expect(part.toolCallId).toBe('toolu_ABC');
      expect(part.toolName).toBe('Bash');
      expect(part.args).toEqual({ cmd: 'ls' });
    });

    it('falls back to msg.id when toolUseId missing', () => {
      const out = convertToThreadMessage({
        id: 'tu-fallback',
        taskId: 't',
        type: 'tool_use',
        content: '',
        toolName: 'Read',
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      const part = out.content[0] as { toolCallId: string };
      expect(part.toolCallId).toBe('tu-fallback');
    });

    it('falls back to "unknown" tool name when missing', () => {
      const out = convertToThreadMessage({
        id: 'tu-noname',
        taskId: 't',
        type: 'tool_use',
        content: '',
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      const part = out.content[0] as { toolName: string };
      expect(part.toolName).toBe('unknown');
    });
  });

  describe('tool_result → tool-call part with result', () => {
    it('correlates with tool_use via toolUseId', () => {
      const out = convertToThreadMessage({
        id: 'tr1',
        taskId: 't',
        type: 'tool_result',
        content: 'stdout here',
        toolUseId: 'toolu_ABC',
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      const part = out.content[0] as { toolCallId: string; result: unknown; isError: boolean };
      expect(part.toolCallId).toBe('toolu_ABC');
      expect(part.result).toBe('stdout here');
      expect(part.isError).toBe(false);
    });

    it('surfaces isError=true when the result is an error', () => {
      const out = convertToThreadMessage({
        id: 'tr-err',
        taskId: 't',
        type: 'tool_result',
        content: 'ENOENT',
        toolUseId: 'toolu_DEF',
        isError: true,
        timestamp: '2026-04-18T00:00:00.000Z',
      });
      const part = out.content[0] as { isError: boolean };
      expect(part.isError).toBe(true);
    });
  });

  describe('createdAt', () => {
    it('parses the timestamp into a Date', () => {
      const out = convertToThreadMessage({
        id: 'x',
        taskId: 't',
        type: 'user',
        content: 'hi',
        timestamp: '2026-04-18T12:34:56.000Z',
      });
      expect(out.createdAt?.toISOString()).toBe('2026-04-18T12:34:56.000Z');
    });

    it('falls back to new Date() when timestamp missing', () => {
      const out = convertToThreadMessage({
        id: 'x',
        taskId: 't',
        type: 'user',
        content: 'hi',
        // @ts-expect-error — exercising defensive branch for malformed persisted data
        timestamp: undefined,
      });
      expect(out.createdAt).toBeInstanceOf(Date);
    });
  });

  describe('purity', () => {
    it('does not mutate the input message', () => {
      const input: ChatMessage = {
        id: 'p',
        taskId: 't',
        type: 'tool_use',
        content: '',
        toolName: 'Bash',
        toolUseId: 'toolu_X',
        toolInput: { cmd: 'pwd' },
        timestamp: '2026-04-18T00:00:00.000Z',
      };
      const snapshot = JSON.parse(JSON.stringify(input));
      convertToThreadMessage(input);
      expect(input).toEqual(snapshot);
    });
  });
});

describe('isSystemInitBlob / visibleChatMessages', () => {
  it('flags system/init blobs', () => {
    expect(
      isSystemInitBlob({
        id: 's',
        taskId: 't',
        type: 'system',
        content: '{"type":"system","subtype":"init","session_id":"x"}',
        timestamp: '2026-04-18T00:00:00.000Z',
      })
    ).toBe(true);
  });

  it('does not flag short "Session started" lines', () => {
    expect(
      isSystemInitBlob({
        id: 's',
        taskId: 't',
        type: 'system',
        content: 'Session started · claude-opus-4-7',
        timestamp: '2026-04-18T00:00:00.000Z',
      })
    ).toBe(false);
  });

  it('does not flag non-system messages', () => {
    expect(
      isSystemInitBlob({
        id: 's',
        taskId: 't',
        type: 'assistant',
        content: '{"foo":1}',
        timestamp: '2026-04-18T00:00:00.000Z',
      })
    ).toBe(false);
  });

  it('filters system/init blobs while keeping short system lines', () => {
    const msgs: ChatMessage[] = [
      {
        id: 'a',
        taskId: 't',
        type: 'system',
        content: '{"type":"system","subtype":"init","session_id":"x"}',
        timestamp: '2026-04-18T00:00:00.000Z',
      },
      {
        id: 'b',
        taskId: 't',
        type: 'system',
        content: 'Session started · claude-opus-4-7',
        timestamp: '2026-04-18T00:00:01.000Z',
      },
      {
        id: 'c',
        taskId: 't',
        type: 'assistant',
        content: 'hi',
        timestamp: '2026-04-18T00:00:02.000Z',
      },
    ];
    const out = visibleChatMessages(msgs);
    expect(out.map((m) => m.id)).toEqual(['b', 'c']);
  });
});

/**
 * Fixture-driven contract tests. Each recorded transcript must round-trip
 * through the converter without loss of information relevant to the
 * renderer.
 */

describe('fixture contract — ordering and pairing', () => {
  it('preserves message order for every fixture', () => {
    for (const name of listFixtureNames()) {
      const msgs = loadFixture(name);
      const converted = msgs.map(convertToThreadMessage);
      expect(converted.length, `count mismatch for ${name}`).toBe(msgs.length);
      for (let i = 0; i < msgs.length; i++) {
        expect(converted[i].id, `id mismatch at index ${i} for ${name}`).toBe(msgs[i].id);
      }
    }
  });

  it('every tool_use has a toolCallId matching toolUseId when present', () => {
    for (const name of listFixtureNames()) {
      const msgs = loadFixture(name);
      for (const msg of msgs) {
        if (msg.type !== 'tool_use' && msg.type !== 'tool_result') continue;
        const out = convertToThreadMessage(msg);
        const part = out.content[0] as { toolCallId: string };
        if (msg.toolUseId) {
          expect(part.toolCallId, `fixture ${name} msg ${msg.id}`).toBe(msg.toolUseId);
        } else {
          expect(part.toolCallId, `fixture ${name} msg ${msg.id}`).toBe(msg.id);
        }
      }
    }
  });

  it('askuser-roundtrip fixture has matched tool_use/tool_result pair', () => {
    const msgs = loadFixture('askuser-roundtrip');
    const toolUse = msgs.find((m) => m.type === 'tool_use' && m.toolName === 'AskUserQuestion');
    const toolResult = msgs.find((m) => m.type === 'tool_result');
    expect(toolUse).toBeDefined();
    expect(toolResult).toBeDefined();
    expect(toolUse?.toolUseId).toBeDefined();
    expect(toolResult?.toolUseId).toBe(toolUse?.toolUseId);
    const convUse = convertToThreadMessage(toolUse!);
    const convResult = convertToThreadMessage(toolResult!);
    const usePart = convUse.content[0] as { toolCallId: string };
    const resultPart = convResult.content[0] as { toolCallId: string };
    expect(usePart.toolCallId).toBe(resultPart.toolCallId);
  });

  it('thinking-heavy fixture maps every thinking message to a reasoning part', () => {
    const msgs = loadFixture('thinking-heavy');
    const thinking = msgs.filter((m) => m.type === 'thinking');
    expect(thinking.length).toBeGreaterThan(0);
    for (const t of thinking) {
      const out = convertToThreadMessage(t);
      const part = out.content[0] as { type: string };
      expect(part.type).toBe('reasoning');
    }
  });

  it('resume-scenario fixture preserves pre- and post-resume segments', () => {
    const msgs = loadFixture('resume-scenario');
    const sessionIds = new Set<string>();
    for (const m of msgs) {
      if (m.type !== 'system') continue;
      if (typeof m.content !== 'string') continue;
      if (!m.content.startsWith('{')) continue;
      try {
        const parsed = JSON.parse(m.content) as { session_id?: string };
        if (parsed.session_id) sessionIds.add(parsed.session_id);
      } catch {
        /* ignore */
      }
    }
    expect(sessionIds.size, 'resume fixture should carry >=2 distinct session_ids').toBeGreaterThanOrEqual(2);
    // After filtering init blobs, non-system messages from both segments remain.
    const visible = visibleChatMessages(msgs);
    const userMsgs = visible.filter((m) => m.type === 'user');
    expect(userMsgs.length).toBeGreaterThanOrEqual(2);
  });

  it('short-happy-path → result message converted to assistant role', () => {
    const msgs = loadFixture('short-happy-path');
    const result = msgs.find((m) => m.type === 'result');
    expect(result).toBeDefined();
    const out = convertToThreadMessage(result!);
    expect(out.role).toBe('assistant');
  });

  it('live-task-7f1815f3 ordering: every converted message preserves timestamp ordering', () => {
    const msgs = loadFixture('live-task-7f1815f3');
    for (let i = 1; i < msgs.length; i++) {
      expect(
        new Date(msgs[i].timestamp).getTime(),
        `fixture not sorted at index ${i}`
      ).toBeGreaterThanOrEqual(new Date(msgs[i - 1].timestamp).getTime());
    }
  });

  it('markdown-streaming fixture: partial code fence is carried through unescaped', () => {
    const msgs = loadFixture('markdown-streaming');
    const partial = msgs.find((m) => m.id === 'md-004-stream-incomplete');
    expect(partial).toBeDefined();
    const out = convertToThreadMessage(partial!);
    const part = out.content[0] as { type: string; text: string };
    expect(part.type).toBe('text');
    expect(part.text).toContain('```python');
    expect(part.text).not.toContain('```\n```');
  });
});

describe('ThreadMessageLike assignability', () => {
  it('return type is compatible with ThreadMessageLike', () => {
    const msg: ChatMessage = {
      id: 'x',
      taskId: 't',
      type: 'user',
      content: 'hi',
      timestamp: '2026-04-18T00:00:00.000Z',
    };
    const out: ThreadMessageLike = convertToThreadMessage(msg);
    expect(out).toBeDefined();
  });
});
