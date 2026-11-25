import { vi } from 'vitest';

type Handler = unknown | ((body: unknown) => unknown);

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

export function mockApi(routes: Record<string, Handler>) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (path: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET';
    const body =
      init.body instanceof FormData
        ? Object.fromEntries(init.body.entries())
        : init.body
          ? JSON.parse(init.body as string)
          : undefined;
    calls.push({ method, path, body });
    const handler = routes[`${method} ${path}`];
    if (handler === undefined) {
      return new Response(JSON.stringify({ detail: `no mock for ${method} ${path}` }), {
        status: 404,
        headers: { 'content-type': 'application/json' }
      });
    }
    const value = await (typeof handler === 'function' ? (handler as (b: unknown) => unknown)(body) : handler);
    if (value instanceof Response) return value;
    return new Response(JSON.stringify(value), {
      status: 200,
      headers: { 'content-type': 'application/json' }
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}
