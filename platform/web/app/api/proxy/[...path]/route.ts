// BFF proxy: client component 走 /api/proxy/<path> → 服务端读 httpOnly cookie 拼 Bearer 转发到上游 API。
// 解决：浏览器 fetch 跨域到 8010 时拿不到 httpOnly cookie，client fetch 401。
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { getApiBaseUrl } from "../../../../lib/config";

const ACCESS_TOKEN_COOKIE = "farm_access_token";
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "host",
  "content-length",
]);

async function forward(request: Request, path: string[]) {
  const upstream = getApiBaseUrl().replace(/\/$/, "");
  const subPath = path.map((seg) => encodeURIComponent(seg)).join("/");
  const search = new URL(request.url).search;
  const url = `${upstream}/api/${subPath}${search}`;

  const token = cookies().get(ACCESS_TOKEN_COOKIE)?.value ?? "";
  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (HOP_BY_HOP.has(lower)) return;
    if (lower === "cookie") return; // upstream 不需要 web 域 cookie
    headers[key] = value;
  });
  if (token) headers.Authorization = `Bearer ${token}`;

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  const upstreamRes = await fetch(url, init);
  const buf = await upstreamRes.arrayBuffer();
  const resHeaders = new Headers();
  upstreamRes.headers.forEach((value, key) => {
    if (HOP_BY_HOP.has(key.toLowerCase())) return;
    resHeaders.set(key, value);
  });
  return new NextResponse(buf, { status: upstreamRes.status, headers: resHeaders });
}

export async function GET(request: Request, ctx: { params: { path: string[] } }) {
  return forward(request, ctx.params.path ?? []);
}
export async function POST(request: Request, ctx: { params: { path: string[] } }) {
  return forward(request, ctx.params.path ?? []);
}
export async function PUT(request: Request, ctx: { params: { path: string[] } }) {
  return forward(request, ctx.params.path ?? []);
}
export async function PATCH(request: Request, ctx: { params: { path: string[] } }) {
  return forward(request, ctx.params.path ?? []);
}
export async function DELETE(request: Request, ctx: { params: { path: string[] } }) {
  return forward(request, ctx.params.path ?? []);
}

export const dynamic = "force-dynamic";
