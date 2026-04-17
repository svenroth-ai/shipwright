import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, beforeEach } from 'vitest';
import { createElement } from 'react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/mocks/server';
import { useChatSettings, upgradeLegacyModelAlias } from './useChatSettings';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useChatSettings — Sub-iterate C model unification', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('upgradeLegacyModelAlias maps coarse alias to first KNOWN_MODEL of that family', () => {
    expect(upgradeLegacyModelAlias('opus')).toMatch(/^claude-opus-/);
    expect(upgradeLegacyModelAlias('sonnet')).toMatch(/^claude-sonnet-/);
    expect(upgradeLegacyModelAlias('haiku')).toMatch(/^claude-haiku-/);
  });

  it('upgradeLegacyModelAlias returns null for concrete ids', () => {
    expect(upgradeLegacyModelAlias('claude-opus-4-7')).toBeNull();
    expect(upgradeLegacyModelAlias(null)).toBeNull();
    expect(upgradeLegacyModelAlias('')).toBeNull();
  });

  it('silently upgrades legacy alias in localStorage on first read', () => {
    localStorage.setItem('chat-model', JSON.stringify('opus'));
    server.use(
      http.get('/api/settings', () => HttpResponse.json({ data: {} })),
    );
    const { result } = renderHook(() => useChatSettings(), { wrapper: createWrapper() });
    expect(result.current.model).toMatch(/^claude-opus-/);
    // Persistence: the upgraded value is written back.
    expect(JSON.parse(localStorage.getItem('chat-model')!)).toMatch(/^claude-opus-/);
  });

  it('hydrates model from settings.defaultModel when localStorage is empty', async () => {
    server.use(
      http.get('/api/settings', () =>
        HttpResponse.json({ data: { defaultModel: 'claude-sonnet-4-6' } }),
      ),
    );
    const { result } = renderHook(() => useChatSettings(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.model).toBe('claude-sonnet-4-6'));
    expect(JSON.parse(localStorage.getItem('chat-model')!)).toBe('claude-sonnet-4-6');
  });

  it('does NOT overwrite explicit concrete id with settings.defaultModel', async () => {
    localStorage.setItem('chat-model', JSON.stringify('claude-opus-4-7'));
    server.use(
      http.get('/api/settings', () =>
        HttpResponse.json({ data: { defaultModel: 'claude-sonnet-4-6' } }),
      ),
    );
    const { result } = renderHook(() => useChatSettings(), { wrapper: createWrapper() });
    // Give the settings query a tick — user's explicit pick must win.
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current.model).toBe('claude-opus-4-7');
  });

  it('setModel persists concrete id and updates state', () => {
    server.use(
      http.get('/api/settings', () => HttpResponse.json({ data: {} })),
    );
    const { result } = renderHook(() => useChatSettings(), { wrapper: createWrapper() });
    act(() => result.current.setModel('claude-haiku-4-5'));
    expect(result.current.model).toBe('claude-haiku-4-5');
    expect(JSON.parse(localStorage.getItem('chat-model')!)).toBe('claude-haiku-4-5');
  });

  it('falls back to claude-opus-4-7 when no stored value and no server default', () => {
    server.use(
      http.get('/api/settings', () => HttpResponse.json({ data: {} })),
    );
    const { result } = renderHook(() => useChatSettings(), { wrapper: createWrapper() });
    expect(result.current.model).toBe('claude-opus-4-7');
  });

  it('never returns the coarse alias form after a legacy value is migrated', () => {
    localStorage.setItem('chat-model', JSON.stringify('sonnet'));
    server.use(
      http.get('/api/settings', () => HttpResponse.json({ data: {} })),
    );
    const { result } = renderHook(() => useChatSettings(), { wrapper: createWrapper() });
    expect(result.current.model).not.toBe('sonnet');
    expect(result.current.model).not.toBe('opus');
    expect(result.current.model).not.toBe('haiku');
    expect(result.current.model.startsWith('claude-')).toBe(true);
  });
});
