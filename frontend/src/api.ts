import { csrfStore } from "./csrfStore";
import type { ApiError } from "./types";

const BASE = "/funding/api";

export interface ApiResult<T> {
  data?: T;
  error?: ApiError;
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    if (body?.error) return body.error as ApiError;
    if (body?.detail?.code) return body.detail as ApiError;
    return { code: "server_error", message: `HTTP ${res.status}` };
  } catch {
    return { code: "server_error", message: `HTTP ${res.status}` };
  }
}

async function request<T>(path: string, init: RequestInit): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, { ...init, credentials: "same-origin" });
    if (!res.ok) return { error: await parseError(res) };
    if (res.status === 204) return { data: undefined as unknown as T };
    return { data: (await res.json()) as T };
  } catch (e) {
    return { error: { code: "network_error", message: (e as Error).message } };
  }
}

async function writeRequest<T>(method: string, path: string, body?: unknown): Promise<ApiResult<T>> {
  const token = await csrfStore.getToken();
  return request<T>(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Funding-Token": token,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) => writeRequest<T>("POST", path, body),
  delete: <T>(path: string) => writeRequest<T>("DELETE", path),
};
