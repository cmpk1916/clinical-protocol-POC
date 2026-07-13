import { NextResponse } from "next/server";


const identityHeaders = {
  "X-Tenant-ID": "synthetic-demo",
  "X-Actor-ID": "local-writer",
};


export async function POST(
  _request: Request,
  context: { params: Promise<{ studyId: string }> },
) {
  const { studyId } = await context.params;
  const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";
  const stateResponse = await fetch(`${apiUrl}/test/studies/${encodeURIComponent(studyId)}/state`, {
    cache: "no-store",
  });
  if (!stateResponse.ok) {
    return NextResponse.json({ detail: { blockers: ["Synthetic study is not seeded"] } }, { status: 409 });
  }
  const state = (await stateResponse.json()) as { exportCommand?: Record<string, unknown> };
  if (!state.exportCommand) {
    return NextResponse.json({ detail: { blockers: ["Export command is unavailable"] } }, { status: 409 });
  }
  const response = await fetch(`${apiUrl}/api/studies/${encodeURIComponent(studyId)}/exports`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...identityHeaders },
    body: JSON.stringify(state.exportCommand),
    cache: "no-store",
  });
  const payload = await response.json();
  if (response.ok && Array.isArray(payload.artifacts)) {
    payload.artifacts = payload.artifacts.map((artifact: { id: string }) => ({
      ...artifact,
      downloadUrl: `/api/artifacts/${artifact.id}`,
    }));
  }
  return NextResponse.json(payload, { status: response.status });
}
