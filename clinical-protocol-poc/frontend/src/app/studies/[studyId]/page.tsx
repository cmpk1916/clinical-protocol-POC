import { WorkspaceGuide } from "../../../features/studies/WorkspaceGuide";
import { toWorkspaceSummary } from "../../../lib/api";
import { backendFetch } from "../../../lib/backend";

export default async function StudyWorkspacePage({
  params,
}: Readonly<{ params: Promise<{ studyId: string }> }>) {
  const { studyId } = await params;
  const response = await backendFetch(`studies/${encodeURIComponent(studyId)}/workspace`);
  if (!response.ok) {
    return (
      <main className="workspace-shell">
        <h1>Workspace unavailable</h1>
        <p role="alert">The study could not be loaded. Return to the study dashboard and try again.</p>
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a href="/">All studies</a>
      </main>
    );
  }
  const summary = toWorkspaceSummary(await response.json());
  return <WorkspaceGuide initialSummary={summary} />;
}
