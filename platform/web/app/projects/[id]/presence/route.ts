import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getApiBaseUrl } from "../../../../lib/config";

const ACCESS_TOKEN_COOKIE = "farm_access_token";
const LEGACY_ACCESS_TOKEN_COOKIE = "access_token";
const MOJIBAKE_ACCESS_TOKEN_COOKIE = "搴勫洯璁块棶浠ょ墝";

export const dynamic = "force-dynamic";

export async function POST(request: Request, context: { params: { id: string } }) {
  const projectId = String(context.params.id || "").trim();
  if (!projectId) {
    return NextResponse.json({ error: "project id required" }, { status: 400 });
  }

  let body: Record<string, unknown> = {};
  try {
    const parsed = await request.json();
    if (parsed && typeof parsed === "object") body = parsed as Record<string, unknown>;
  } catch {
    body = {};
  }

  const cookieStore = cookies();
  const accessToken =
    cookieStore.get(ACCESS_TOKEN_COOKIE)?.value ??
    cookieStore.get(LEGACY_ACCESS_TOKEN_COOKIE)?.value ??
    cookieStore.get(MOJIBAKE_ACCESS_TOKEN_COOKIE)?.value;
  if (!accessToken) {
    return NextResponse.json({ error: "authentication required" }, { status: 401 });
  }

  const response = await fetch(`${getApiBaseUrl()}/api/projects/${encodeURIComponent(projectId)}/presence`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ path: String(body.path ?? `/projects/${projectId}`).slice(0, 500) }),
  });

  const payload = await response.json().catch(() => null);
  return NextResponse.json(payload ?? {}, { status: response.status });
}
