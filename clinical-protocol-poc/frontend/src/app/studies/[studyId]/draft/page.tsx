import {
  demoExportState,
  demoPassages,
  demoScorecard,
} from "../../../../lib/api";
import { ProtocolNavigator } from "../../../../features/drafting/ProtocolNavigator";
import { PassageEditor } from "../../../../features/drafting/PassageEditor";
import { Scorecard } from "../../../../features/quality/Scorecard";
import { ExportPanel } from "../../../../features/export/ExportPanel";
import type { DraftPassage, ExportState } from "../../../../lib/types";

type TestState = {
  passage: DraftPassage;
  export: ExportState;
};

async function getDraftState(studyId: string): Promise<TestState> {
  const fallback = { passage: demoPassages[0], export: demoExportState };
  const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";

  try {
    const response = await fetch(`${apiUrl}/test/studies/${studyId}/state`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return fallback;
    }
    return (await response.json()) as TestState;
  } catch {
    return fallback;
  }
}

export default async function DraftPage({
  params,
}: Readonly<{ params: Promise<{ studyId: string }> }>) {
  const { studyId } = await params;
  const state = await getDraftState(studyId);
  const passages = [state.passage];

  return (
    <main>
      <ProtocolNavigator passages={passages} />
      {passages.map((passage) => (
        <PassageEditor key={passage.id} passage={passage} />
      ))}
      <Scorecard card={demoScorecard} />
      <ExportPanel studyId={studyId} state={state.export} />
    </main>
  );
}
