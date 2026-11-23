import { afterEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { api, ApiError, SessionExpiredError } from './client';
import { sessionExpired } from '#lib/session.ts';
import { mockApi } from '#lib/test/mockApi.ts';

describe('api client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionExpired.set(false);
  });

  it('get returns parsed json', async () => {
    mockApi({ 'GET /api/costs': { cap_today: 0.5 } });
    expect(await api.get('/api/costs')).toEqual({ cap_today: 0.5 });
  });

  it('post sends the body as json', async () => {
    const { calls } = mockApi({ 'POST /api/x': { ok: true } });
    await api.post('/api/x', { a: 1 });
    expect(calls).toEqual([{ method: 'POST', path: '/api/x', body: { a: 1 } }]);
  });

  it('throws SessionExpiredError for an html response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('<html>login</html>', { headers: { 'content-type': 'text/html' } }))
    );
    await expect(api.get('/api/costs')).rejects.toBeInstanceOf(SessionExpiredError);
    expect(get(sessionExpired)).toBe(true);
  });

  it('throws SessionExpiredError for a followed redirect', async () => {
    const res = new Response('{}', { headers: { 'content-type': 'application/json' } });
    Object.defineProperty(res, 'redirected', { value: true });
    vi.stubGlobal('fetch', vi.fn(async () => res));
    await expect(api.get('/api/costs')).rejects.toBeInstanceOf(SessionExpiredError);
  });

  it('throws ApiError with the detail of a json error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: 'Nicht gefunden' }), {
            status: 404,
            headers: { 'content-type': 'application/json' }
          })
      )
    );
    const err = (await api.get('/api/x').catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.message).toBe('Nicht gefunden');
    expect(get(sessionExpired)).toBe(false);
  });
});
