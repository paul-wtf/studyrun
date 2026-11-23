import { sessionExpired } from '#lib/session.ts';

export class ApiError extends Error {
  constructor(
    public status: number,
    public path: string,
    detail?: string
  ) {
    super(detail ?? `API ${status} for ${path}`);
  }
}

export class SessionExpiredError extends Error {
  constructor() {
    super('Sitzung abgelaufen');
  }
}

function expire(): never {
  sessionExpired.set(true);
  throw new SessionExpiredError();
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: 'include',
    headers: body === undefined ? undefined : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (res.redirected || res.type === 'opaqueredirect' || res.status === 401) expire();
  const isJson = (res.headers.get('content-type') ?? '').includes('application/json');
  if (!res.ok) {
    const detail = isJson ? ((await res.json().catch(() => null)) as { detail?: unknown } | null)?.detail : undefined;
    throw new ApiError(res.status, path, typeof detail === 'string' ? detail : undefined);
  }
  if (!isJson) expire();
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  del: <T>(path: string) => request<T>('DELETE', path)
};

export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Unbekannter Fehler';
}

export function isStale(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 409 || err.status === 404);
}
