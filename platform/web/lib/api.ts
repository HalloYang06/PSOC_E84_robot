import { getApiBaseUrl, shouldUseMockData } from "./config";
import * as mock from "./mock/data";

export type ApiErrorShape = {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
  meta?: {
    request_id?: string;
  };
};

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;
  requestId?: string;

  constructor(params: {
    code: string;
    message: string;
    status: number;
    details?: unknown;
    requestId?: string;
  }) {
    super(params.message);
    this.code = params.code;
    this.status = params.status;
    this.details = params.details;
    this.requestId = params.requestId;
  }
}

async function parseJsonSafe(res: Response): Promise<any> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

async function request<T>(
  path: string,
  init?: RequestInit & { json?: unknown }
): Promise<T> {
  if (shouldUseMockData()) {
    return mock.handleMockRequest<T>(path, init);
  }

  const url = new URL(path, getApiBaseUrl());
  const headers: Record<string, string> = {
    Accept: "application/json"
  };

  let body: BodyInit | undefined;
  if (init?.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }

  const res = await fetch(url.toString(), {
    ...init,
    headers: { ...headers, ...(init?.headers || {}) },
    body
  });

  const data = await parseJsonSafe(res);
  if (!res.ok) {
    const maybe: ApiErrorShape | null = data;
    throw new ApiError({
      code: maybe?.error?.code || "HTTP_ERROR",
      message: maybe?.error?.message || `HTTP ${res.status}`,
      status: res.status,
      details: maybe?.error?.details,
      requestId: maybe?.meta?.request_id
    });
  }

  // Our API spec wraps data under {data}, but allow raw for health endpoints.
  if (data && typeof data === "object" && "data" in data) return data.data as T;
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, json?: unknown) =>
    request<T>(path, { method: "POST", json }),
  patch: <T>(path: string, json?: unknown) =>
    request<T>(path, { method: "PATCH", json }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" })
};
