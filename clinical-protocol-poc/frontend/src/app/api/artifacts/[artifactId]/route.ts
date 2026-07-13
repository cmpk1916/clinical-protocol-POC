import { NextResponse } from "next/server";


export async function GET(
  _request: Request,
  context: { params: Promise<{ artifactId: string }> },
) {
  const { artifactId } = await context.params;
  const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(`${apiUrl}/api/export-artifacts/${encodeURIComponent(artifactId)}`, {
    headers: { "X-Tenant-ID": "synthetic-demo", "X-Actor-ID": "local-writer" },
    cache: "no-store",
  });
  if (!response.ok) {
    return NextResponse.json({ code: "ARTIFACT_NOT_FOUND" }, { status: response.status });
  }
  return new NextResponse(await response.arrayBuffer(), {
    status: 200,
    headers: {
      "Content-Type": response.headers.get("content-type") ?? "application/octet-stream",
      "Content-Disposition": response.headers.get("content-disposition") ?? "attachment",
    },
  });
}
