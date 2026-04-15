import { describe, it, expect } from 'vitest';
import { extractAskUserPayload, serializePartAnswers } from './askUserPayload';
import type { InboxItemPart } from '../types/inbox';

describe('extractAskUserPayload', () => {
  it('extracts a single question from the real Claude Code schema as one part', () => {
    // Shape verified against a live chat-history jsonl dump on 2026-04-13.
    const toolInput = {
      questions: [
        {
          question: 'What priority should this task have?',
          header: 'Priority',
          options: [
            { label: 'High', description: 'Blocks others' },
            { label: 'Medium', description: 'Soon' },
            { label: 'Low' },
          ],
          multiSelect: false,
        },
      ],
    };
    const payload = extractAskUserPayload(toolInput);
    expect(payload.parts).toHaveLength(1);
    expect(payload.parts[0].question).toBe('What priority should this task have?');
    expect(payload.parts[0].options).toEqual(['High', 'Medium', 'Low']);
    expect(payload.parts[0].header).toBe('Priority');
    // multiSelect: false → omitted, not stored as `false`
    expect(payload.parts[0].allowMultiple).toBeUndefined();
  });

  it('extracts ALL parts when Claude asks multiple questions in one tool_use (regression: dropped 2..N)', () => {
    const payload = extractAskUserPayload({
      questions: [
        { question: 'First?', header: 'A', options: [{ label: 'Y' }] },
        { question: 'Second?', header: 'B' },
        { question: 'Third?', header: 'C', multiSelect: true, options: [{ label: 'X' }, { label: 'Z' }] },
      ],
    });
    expect(payload.parts).toHaveLength(3);
    expect(payload.parts[0].question).toBe('First?');
    expect(payload.parts[1].question).toBe('Second?');
    expect(payload.parts[2].question).toBe('Third?');
    expect(payload.parts[2].allowMultiple).toBe(true);
    expect(payload.parts[2].options).toEqual(['X', 'Z']);
  });

  it('flags allowMultiple when multiSelect boolean is true', () => {
    const payload = extractAskUserPayload({
      questions: [
        {
          question: 'Pick all that apply',
          options: [{ label: 'A' }, { label: 'B' }],
          multiSelect: true,
        },
      ],
    });
    expect(payload.parts[0].allowMultiple).toBe(true);
  });

  it('falls back to legacy flat schema { question, context, options: string[] } as a single part', () => {
    const toolInput = {
      question: 'Continue?',
      context: 'About to drop table users',
      options: ['Yes', 'No'],
    };
    const payload = extractAskUserPayload(toolInput);
    expect(payload.parts).toHaveLength(1);
    expect(payload.parts[0].question).toBe('Continue?');
    expect(payload.parts[0].context).toBe('About to drop table users');
    expect(payload.parts[0].options).toEqual(['Yes', 'No']);
  });

  it('handles object-form options in legacy schema', () => {
    const toolInput = {
      question: 'Pick one',
      options: [{ label: 'A' }, { label: 'B' }],
    };
    const payload = extractAskUserPayload(toolInput);
    expect(payload.parts[0].options).toEqual(['A', 'B']);
  });

  it('strips description from object-form options (label-only)', () => {
    const payload = extractAskUserPayload({
      questions: [
        {
          question: 'Pick',
          options: [{ label: 'High', description: 'urgent' }, { label: 'Low' }],
        },
      ],
    });
    expect(payload.parts[0].options).toEqual(['High', 'Low']);
  });

  it('returns empty parts list for missing input', () => {
    const payload = extractAskUserPayload(undefined);
    expect(payload.parts).toEqual([]);
  });

  it('returns empty parts list for unparseable shape', () => {
    const payload = extractAskUserPayload({ banana: true });
    expect(payload.parts).toEqual([]);
  });

  it('returns empty parts list for an empty questions array', () => {
    const payload = extractAskUserPayload({ questions: [] });
    expect(payload.parts).toEqual([]);
  });
});

describe('serializePartAnswers', () => {
  it('joins parts with header + answer using markdown headings', () => {
    const parts: InboxItemPart[] = [
      { question: 'Q1?', header: 'Priority', answer: 'High' },
      { question: 'Q2?', header: 'Owner', answer: 'Alice' },
    ];
    expect(serializePartAnswers(parts)).toBe('## Priority\nHigh\n\n## Owner\nAlice');
  });

  it('uses "Question N" fallback when header is missing', () => {
    const parts: InboxItemPart[] = [
      { question: 'Q1?', answer: 'A' },
      { question: 'Q2?', header: 'Specific', answer: 'B' },
      { question: 'Q3?', answer: 'C' },
    ];
    const out = serializePartAnswers(parts);
    expect(out).toContain('## Question 1\nA');
    expect(out).toContain('## Specific\nB');
    expect(out).toContain('## Question 3\nC');
  });

  it('disambiguates duplicate headers with (1), (2) suffixes', () => {
    const parts: InboxItemPart[] = [
      { question: 'A?', header: 'Setting', answer: 'on' },
      { question: 'B?', header: 'Setting', answer: 'off' },
    ];
    expect(serializePartAnswers(parts)).toBe('## Setting (1)\non\n\n## Setting (2)\noff');
  });

  it('preserves multi-line answers verbatim without code-fence wrapping', () => {
    const parts: InboxItemPart[] = [
      { question: 'Notes?', header: 'Notes', answer: 'line1\nline2\nline3' },
    ];
    expect(serializePartAnswers(parts)).toBe('## Notes\nline1\nline2\nline3');
  });

  it('keeps multi-select comma-joined answers on one line (UI passes them as comma string)', () => {
    const parts: InboxItemPart[] = [
      { question: 'Pick all', header: 'Tags', allowMultiple: true, answer: 'one, two, three' },
    ];
    expect(serializePartAnswers(parts)).toBe('## Tags\none, two, three');
  });

  it('emits "(skipped)" body for empty optional answers', () => {
    const parts: InboxItemPart[] = [
      { question: 'Optional?', header: 'Notes', answer: '' },
    ];
    expect(serializePartAnswers(parts)).toBe('## Notes\n(skipped)');
  });
});
