// 在 client component 里发请求用这个：把 /api/<x> 换成 /api/proxy/<x>，
// 让请求落到 web 同源的 BFF proxy（route.ts 会拼 Authorization 转发到上游 8010）。
export function apiClientUrl(path: string): string {
  if (!path) return "/api/proxy";
  if (path.startsWith("/api/")) {
    return `/api/proxy/${path.slice(5)}`;
  }
  if (path.startsWith("api/")) {
    return `/api/proxy/${path.slice(4)}`;
  }
  if (path.startsWith("/")) return `/api/proxy${path}`;
  return `/api/proxy/${path}`;
}
