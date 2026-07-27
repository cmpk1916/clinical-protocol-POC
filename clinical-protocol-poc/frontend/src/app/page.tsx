import { StudyDashboard } from "../features/studies/StudyDashboard";
import { toWorkspaceSummary, type WorkspacePayload } from "../lib/api";
import { backendFetch } from "../lib/backend";
import type { StudySummary } from "../lib/types";

type StudyPayload = {
  id: string;
  name: string;
  version: number;
  lifecycle: "active" | "archived";
  updated_at: string;
  archived_at: string | null;
  workspace?: WorkspacePayload;
};

async function loadStudies(lifecycle: "active" | "archived"): Promise<StudySummary[]> {
  const response = await backendFetch(`studies?lifecycle=${lifecycle}`);
  if (!response.ok) throw new Error(`Unable to load ${lifecycle} studies`);
  const payload = (await response.json()) as { items: StudyPayload[] };
  return payload.items.map((study) => ({
    id: study.id,
    name: study.name,
    version: study.version,
    lifecycle: study.lifecycle,
    updatedAt: study.updated_at,
    archivedAt: study.archived_at,
    workspace: study.workspace ? toWorkspaceSummary(study.workspace) : undefined,
  }));
}

export default async function Home() {
  const [active, archived] = await Promise.all([
    loadStudies("active"),
    loadStudies("archived"),
  ]);
  return <StudyDashboard initialActive={active} initialArchived={archived} />;
}
