import { getApiBaseUrl } from "./config";

type RequestBody = Record<string, unknown> | Array<unknown> | string | number | boolean | null;

export async function requestApiJson<T>(path: string, options?: {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: RequestBody;
  headers?: Record<string, string>;
}) {
  const headers = new Headers(options?.headers);
  const method = options?.method ?? "GET";
  const hasBody = options?.body !== undefined && options?.body !== null;

  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method,
    headers,
    body: hasBody ? JSON.stringify(options?.body) : undefined,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const json = await response.json();
  return (json && typeof json === "object" && "data" in json ? json.data : json) as T;
}
