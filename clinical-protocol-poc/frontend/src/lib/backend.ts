export function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";
  const headers = new Headers(init.headers);
  headers.set("X-Tenant-ID", process.env.LOCAL_TENANT_ID ?? "local-poc");
  headers.set("X-Actor-ID", process.env.LOCAL_ACTOR_ID ?? "local-writer");

  return fetch(`${apiUrl}/api/${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}
