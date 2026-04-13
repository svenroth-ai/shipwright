import { describe, it, expect } from 'vitest';
import { extractAskUserPayload } from './askUserPayload';

describe('extractAskUserPayload', () => {
  it('extracts from the Claude Code AskUserQuestion schema (questions[0].question + multiSelect.options)', () => {
    const toolInput = {
      questions: [
        {
          header: 'Priority',
          question: 'What priority should this task have?',
          multiSelect: {
            mode: 'single',
            options: [
              { label: 'High', description: 'Blocks others' },
              { label: 'Medium', description: 'Soon' },
              { label: 'Low' },
            ],
          },
        },
      ],
    };
    const payload = extractAskUserPayload(toolInput);
    expect(payload.question).toBe('What priority should this task have?');
    expect(payload.options).toEqual(['High', 'Medium', 'Low']);
    expect(payload.header).toBe('Priority');
  });

  it('falls back to legacy flat schema { question, context, options: string[] }', () => {
    const toolInput = {
      question: 'Continue?',
      context: 'About to drop table users',
      options: ['Yes', 'No'],
    };
    const payload = extractAskUserPayload(toolInput);
    expect(payload.question).toBe('Continue?');
    expect(payload.context).toBe('About to drop table users');
    expect(payload.options).toEqual(['Yes', 'No']);
  });

  it('handles object-form options in legacy schema', () => {
    const toolInput = {
      question: 'Pick one',
      options: [{ label: 'A' }, { label: 'B' }],
    };
    const payload = extractAskUserPayload(toolInput);
    expect(payload.options).toEqual(['A', 'B']);
  });

  it('returns empty question and no options for missing input', () => {
    const payload = extractAskUserPayload(undefined);
    expect(payload.question).toBe('');
    expect(payload.options).toBeUndefined();
  });

  it('returns empty question for unparseable shape', () => {
    const payload = extractAskUserPayload({ banana: true });
    expect(payload.question).toBe('');
    expect(payload.options).toBeUndefined();
  });

  it('handles an empty questions array (treats as missing)', () => {
    const payload = extractAskUserPayload({ questions: [] });
    expect(payload.question).toBe('');
  });

  it('picks the first question when multiple are present', () => {
    const payload = extractAskUserPayload({
      questions: [
        { question: 'First' },
        { question: 'Second' },
      ],
    });
    expect(payload.question).toBe('First');
  });
});
