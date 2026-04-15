import { describe, it, expect } from 'vitest';
import { formatModelLabel } from './formatModelLabel';

describe('formatModelLabel', () => {
  it('formats full opus 4.5 cli id with date suffix', () => {
    expect(formatModelLabel('claude-opus-4-5-20251101')).toBe('Opus 4.5');
  });

  it('formats sonnet 4.6 shorthand', () => {
    expect(formatModelLabel('claude-sonnet-4-6')).toBe('Sonnet 4.6');
  });

  it('formats haiku 4.5 shorthand', () => {
    expect(formatModelLabel('claude-haiku-4-5')).toBe('Haiku 4.5');
  });

  it('falls back to "Claude" on undefined input', () => {
    expect(formatModelLabel(undefined)).toBe('Claude');
  });

  it('falls back to "Claude" on null input', () => {
    expect(formatModelLabel(null)).toBe('Claude');
  });

  it('falls back to "Claude" on empty string', () => {
    expect(formatModelLabel('')).toBe('Claude');
  });

  it('falls back to "Claude" on malformed input', () => {
    expect(formatModelLabel('gpt-5')).toBe('Claude');
    expect(formatModelLabel('claude-opus')).toBe('Claude');
    expect(formatModelLabel('claude-foo-4-5')).toBe('Claude');
  });

  it('is case-insensitive on the family token', () => {
    expect(formatModelLabel('claude-OPUS-4-5')).toBe('Opus 4.5');
  });
});
