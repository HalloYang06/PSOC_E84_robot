function pickServerSideApiBaseUrl(): string | null {
  if (typeof window !== "undefined") return null;
  const internalBaseUrl = process.env.INTERNAL_API_BASE_URL?.trim();
  return internalBaseUrl || null;
}

export function getApiBaseUrl(): string {
  return pickServerSideApiBaseUrl() || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8010";
}

export function useMockData(): boolean {
  const v = process.env.NEXT_PUBLIC_USE_MOCK;
  return v === "1" || v === "true";
}
