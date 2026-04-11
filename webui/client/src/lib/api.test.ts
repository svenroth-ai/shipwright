import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/mocks/server';
import { apiFetch, apiPost, ApiError } from './api';

describe('apiFetch', () => {
  it('returns unwrapped data on success', async () => {
    server.use(
      http.get('/api/test', () =>
        HttpResponse.json({ data: { message: 'hello' } }),
      ),
    );

    const result = await apiFetch<{ message: string }>('/test');
    expect(result).toEqual({ message: 'hello' });
  });

  it('throws ApiError on failure', async () => {
    server.use(
      http.get('/api/fail', () =>
        HttpResponse.json({ error: 'Bad request', detail: 'missing field' }, { status: 400 }),
      ),
    );

    await expect(apiFetch('/fail')).rejects.toThrow(ApiError);

    try {
      await apiFetch('/fail');
    } catch (e) {
      const err = e as ApiError;
      expect(err.status).toBe(400);
      expect(err.error).toBe('Bad request');
      expect(err.detail).toBe('missing field');
    }
  });

  it('handles non-JSON error bodies', async () => {
    server.use(
      http.get('/api/error', () => new HttpResponse('Internal Server Error', { status: 500 })),
    );

    await expect(apiFetch('/error')).rejects.toThrow(ApiError);
  });
});

describe('apiPost', () => {
  it('sends JSON body and returns data', async () => {
    server.use(
      http.post('/api/items', async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ data: body });
      }),
    );

    const result = await apiPost<{ name: string }>('/items', { name: 'test' });
    expect(result).toEqual({ name: 'test' });
  });
});
