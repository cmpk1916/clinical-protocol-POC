import { NextResponse } from "next/server";

import { backendFetch } from "../../../../lib/backend";

const allowedPrefixes = ["studies/", "facts/", "passages/", "export-artifacts/"];

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: RouteContext): Promise<Response> {
  const { path: pathParts } = await context.params;
  const path = pathParts.map(encodeURIComponent).join("/");
  if (!allowedPrefixes.some((prefix) => `${path}/`.startsWith(prefix))) {
    return NextResponse.json({ code: "NOT_FOUND" }, { status: 404 });
  }

  const requestUrl = new URL(request.url);
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("x-tenant-id");
  headers.delete("x-actor-id");
  headers.delete("x-identity-timestamp");
  headers.delete("x-identity-signature");
  headers.delete("content-length");

  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : await request.arrayBuffer();
  const response = await backendFetch(`${path}${requestUrl.search}`, {
    method: request.method,
    headers,
    body,
  });

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

export function GET(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export function POST(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export function PUT(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export function PATCH(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export function DELETE(request: Request, context: RouteContext) {
  return proxy(request, context);
}
