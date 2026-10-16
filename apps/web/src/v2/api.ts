// Typed client for /api/v2. Errors arrive as {error: {code, message}}; the owner cookie is sent automatically.
const BASE = "/api/v2";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(message: string, status: number, code: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function call<T>(path: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, { ...init, credentials: "same-origin", signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("The server is not reachable.", 0, "NETWORK");
  }
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    let code = "HTTP";
    try {
      const j = (await res.json()) as { error?: { code?: string; message?: string } };
      if (j.error?.message) message = j.error.message;
      if (j.error?.code) code = j.error.code;
    } catch {
      /* not JSON */
    }
    throw new ApiError(message, res.status, code);
  }
  return (await res.json()) as T;
}

export const get = <T>(path: string, signal?: AbortSignal): Promise<T> => call<T>(path, { method: "GET" }, signal);

export const post = <T>(path: string, body?: object): Promise<T> =>
  call<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

export const upload = <T>(path: string, file: File): Promise<T> =>
  call<T>(`${path}?name=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });

export const url = (path: string): string => BASE + path;

export const newKey = (): string => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
