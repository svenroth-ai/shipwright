import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { usePhaseMapping } from './usePhaseMapping';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('usePhaseMapping', () => {
  it('returns default mapping when no projectId', () => {
    const { result } = renderHook(() => usePhaseMapping(), {
      wrapper: createWrapper(),
    });

    expect(result.current.getStatus('build')).toBe('in_progress');
    expect(result.current.getStatus('test')).toBe('in_review');
    expect(result.current.getStatus('unknown')).toBe('backlog');
  });
});
