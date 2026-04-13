import { describe, it, expect } from 'vitest';
import { collapseAskUserQuestionRun } from './collapseAskUserQuestion';
import type { ChatMessage } from '../types';

function msg(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: 'm',
    taskId: 't',
    type: 'assistant',
    content: '',
    timestamp: '2026-04-13T00:00:00Z',
    ...overrides,
  } as ChatMessage;
}

function askUser(id: string, q = 'pick'): ChatMessage {
  return msg({
    id: `ask-${id}`,
    type: 'tool_use',
    toolName: 'AskUserQuestion',
    toolUseId: id,
    toolInput: { questions: [{ question: q }] },
  });
}

function toolResult(id: string, content = 'Yes'): ChatMessage {
  return msg({
    id: `res-${id}`,
    type: 'tool_result',
    toolUseId: id,
    content,
  });
}

function assistant(text: string): ChatMessage {
  return msg({ id: `a-${text.slice(0, 4)}`, type: 'assistant', content: text });
}

describe('collapseAskUserQuestionRun', () => {
  it('is identity when no AskUserQuestion messages are present', () => {
    const messages = [
      msg({ id: 'u1', type: 'user', content: 'hi' }),
      assistant('hello'),
      msg({ id: 'bash1', type: 'tool_use', toolName: 'Bash', toolUseId: 'toolu_bash', toolInput: { cmd: 'ls' } }),
    ];
    expect(collapseAskUserQuestionRun(messages)).toEqual(messages);
  });

  it('keeps the first pending AskUserQuestion and drops the second one', () => {
    const messages = [
      askUser('toolu_1', 'Vision?'),
      askUser('toolu_2', 'Vision short?'),
    ];
    const out = collapseAskUserQuestionRun(messages);
    expect(out).toHaveLength(1);
    expect(out[0].toolUseId).toBe('toolu_1');
  });

  it('drops assistant markdown fallback text after a pending AskUserQuestion', () => {
    const messages = [
      askUser('toolu_1'),
      assistant('Lass mich wissen: 1. A 2. B 3. C'),
    ];
    const out = collapseAskUserQuestionRun(messages);
    expect(out).toHaveLength(1);
    expect(out[0].toolUseId).toBe('toolu_1');
  });

  it('keeps the AskUserQuestion and its matching tool_result when answered', () => {
    const messages = [askUser('toolu_1'), toolResult('toolu_1', 'chose A')];
    const out = collapseAskUserQuestionRun(messages);
    expect(out).toHaveLength(2);
    expect(out[0].type).toBe('tool_use');
    expect(out[1].type).toBe('tool_result');
  });

  it('resumes normal rendering after the pending question is resolved', () => {
    const messages = [
      askUser('toolu_1'),
      assistant('markdown fallback'), // suppressed
      toolResult('toolu_1'),
      assistant('Great, proceeding.'), // kept — after resolution
    ];
    const out = collapseAskUserQuestionRun(messages);
    expect(out.map((m) => m.id)).toEqual(['ask-toolu_1', 'res-toolu_1', 'a-Grea']);
  });

  it('treats folded tool_use (toolOutput set) as resolved', () => {
    const folded = msg({
      id: 'ask-toolu_1',
      type: 'tool_use',
      toolName: 'AskUserQuestion',
      toolUseId: 'toolu_1',
      toolInput: { questions: [{ question: 'pick' }] },
      toolOutput: 'Yes',
    });
    const messages = [folded, assistant('Great, proceeding.')];
    const out = collapseAskUserQuestionRun(messages);
    expect(out).toHaveLength(2);
    expect(out[1].content).toBe('Great, proceeding.');
  });

  it('passes through non-AskUserQuestion tool_uses during a pending run', () => {
    const messages = [
      askUser('toolu_1'),
      msg({
        id: 'bash1',
        type: 'tool_use',
        toolName: 'Bash',
        toolUseId: 'toolu_bash',
        toolInput: { cmd: 'ls' },
      }),
    ];
    const out = collapseAskUserQuestionRun(messages);
    expect(out).toHaveLength(2);
    expect(out[1].toolName).toBe('Bash');
  });

  it('handles the real iterate-7-live scenario (2 asks + markdown + result)', () => {
    const messages = [
      assistant('Jetzt starte ich das Interview…'),
      askUser('toolu_01FJ1LNg', 'Was für eine Art ToDo App schwebt dir vor? Beschreibe kurz.'),
      askUser('toolu_01PDSMPJ', 'Was für eine Art ToDo App schwebt dir vor?'),
      assistant('Lass mich wissen: 1. Persönliche ToDo App 2. Team 3. Projekt-Management 4. Nische'),
      msg({ id: 'res1', type: 'result', content: 'same markdown' }),
    ];
    const out = collapseAskUserQuestionRun(messages);
    expect(out.map((m) => m.id)).toEqual([
      'a-Jetz',
      'ask-toolu_01FJ1LNg',
    ]);
  });
});
