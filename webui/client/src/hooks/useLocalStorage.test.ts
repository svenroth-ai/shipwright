import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { useLocalStorage } from './useLocalStorage';

beforeEach(() => {
  localStorage.clear();
});

describe('useLocalStorage', () => {
  it('returns default value when key does not exist', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 'default'));
    expect(result.current[0]).toBe('default');
  });

  it('reads existing value from localStorage', () => {
    localStorage.setItem('test-key', JSON.stringify('stored-value'));
    const { result } = renderHook(() => useLocalStorage('test-key', 'default'));
    expect(result.current[0]).toBe('stored-value');
  });

  it('writes value to localStorage', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 'default'));

    act(() => {
      result.current[1]('new-value');
    });

    expect(result.current[0]).toBe('new-value');
    expect(JSON.parse(localStorage.getItem('test-key')!)).toBe('new-value');
  });

  it('handles corrupt data gracefully', () => {
    localStorage.setItem('test-key', '{invalid json');
    const { result } = renderHook(() => useLocalStorage('test-key', 'fallback'));
    expect(result.current[0]).toBe('fallback');
  });

  it('works with object values', () => {
    const { result } = renderHook(() =>
      useLocalStorage('test-key', { width: 500 }),
    );

    act(() => {
      result.current[1]({ width: 700 });
    });

    expect(result.current[0]).toEqual({ width: 700 });
  });
});
