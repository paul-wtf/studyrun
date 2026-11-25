import { sessionExpired } from '#lib/session.ts';

export class ApiError extends Error {
  constructor(
    public status: number,
    public path: string,
    detail?: string,
    public body?: unknown
  ) {
    super(detail ?? `Der Server hat mit Fehler ${status} geantwortet.`);
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

async function request<T>(method: string, path: string, body?: unknown, keepalive = false): Promise<T> {
  const form = body instanceof FormData;
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: 'include',
      redirect: 'manual',
      keepalive,
      headers: body === undefined || form ? undefined : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : form ? body : JSON.stringify(body)
    });
  } catch (e) {
    if (e instanceof TypeError) throw new Error('Keine Verbindung zum Server.');
    throw e;
  }
  if (res.redirected || res.type === 'opaqueredirect' || res.status === 401) expire();
  const isJson = (res.headers.get('content-type') ?? '').includes('application/json');
  if (!res.ok) {
    const parsed = isJson ? ((await res.json().catch(() => null)) as { detail?: unknown } | null) : null;
    const detail = parsed?.detail;
    throw new ApiError(res.status, path, typeof detail === 'string' ? detail : undefined, parsed);
  }
  if (res.status === 204) return undefined as T;
  if (!isJson) expire();
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown, { keepalive = false } = {}) => request<T>('POST', path, body, keepalive),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  del: <T>(path: string) => request<T>('DELETE', path)
};

export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Unbekannter Fehler';
}

export function isStale(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 409 || err.status === 404);
}
