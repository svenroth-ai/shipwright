import { describe, it, expect, beforeEach } from 'vitest';
import { getStored, setStored } from './localStorage';

beforeEach(() => {
  localStorage.clear();
});

// Iterate 14.7.0 — P0.3 localStorage helpers.
describe('getStored', () => {
  it('reads existing JSON value from localStorage', () => {
    localStorage.setItem('k1', JSON.stringify('hello'));
    expect(getStored<string>('k1', 'fallback')).toBe('hello');
  });

  it('returns fallback when key is missing', () => {
    expect(getStored<string | null>('missing-key', null)).toBe(null);
  });

  it('returns fallback when stored value is invalid JSON', () => {
    localStorage.setItem('k1', '{not json');
    expect(getStored<string>('k1', 'fallback')).toBe('fallback');
  });

  it('reads stored null (literal) as null', () => {
    localStorage.setItem('k1', JSON.stringify(null));
    expect(getStored<string | null>('k1', 'fallback')).toBe(null);
  });

  it('reads stored object values', () => {
    localStorage.setItem('k1', JSON.stringify({ x: 1 }));
    expect(getStored<{ x: number }>('k1', { x: 0 })).toEqual({ x: 1 });
  });
});

describe('setStored', () => {
  it('writes JSON-serialised value to localStorage', () => {
    setStored<string>('k1', 'hello');
    expect(localStorage.getItem('k1')).toBe(JSON.stringify('hello'));
  });

  it('writes null as JSON literal (not as absence)', () => {
    setStored<string | null>('k1', null);
    expect(localStorage.getItem('k1')).toBe(JSON.stringify(null));
    // And getStored reads it back correctly
    expect(getStored<string | null>('k1', 'fallback')).toBe(null);
  });

  it('writes object values', () => {
    setStored<{ x: number }>('k1', { x: 42 });
    expect(JSON.parse(localStorage.getItem('k1')!)).toEqual({ x: 42 });
  });
});
