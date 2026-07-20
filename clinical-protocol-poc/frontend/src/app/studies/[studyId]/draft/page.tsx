"use client";

import React, { use, useCallback, useEffect, useState } from "react";

import { ProtocolNavigator } from "../../../../features/drafting/ProtocolNavigator";
import { PassageEditor } from "../../../../features/drafting/PassageEditor";
import { Scorecard } from "../../../../features/quality/Scorecard";
import { ExportPanel } from "../../../../features/export/ExportPanel";
import { protocolDraftingApi, protocolWorkspaceApi } from "../../../../lib/api";
import type { DraftPassage, ExportState, PassageApi, QualityScorecard, WorkspaceSummary } from "../../../../lib/types";

const sections = [
  ["synopsis", "Synopsis"],
  ["objectives_endpoints", "Objectives and endpoints"],
  ["study_design", "Study design"],
  ["eligibility", "Eligibility"],
] as const;

type Section = (typeof sections)[number][0];
type DraftState = {
  passages: DraftPassage[];
  quality: QualityScorecard;
  readOnly: boolean;
  exportCommand: WorkspaceSummary["exportCommand"];
  exportBlockers: string[];
};

export default function DraftPage({
  params,
}: Readonly<{ params: Promise<{ studyId: string }> }>) {
  return <DraftWorkspace studyId={use(params).studyId} />;
}

function DraftWorkspace({ studyId }: Readonly<{ studyId: string }>) {
  const [state, setState] = useState<DraftState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState<Section | null>(null);

  const refresh = useCallback(async () => {
    const [passages, quality, workspace] = await Promise.all([
      protocolDraftingApi.getPassages(studyId),
      protocolDraftingApi.getQuality(studyId),
      protocolWorkspaceApi.getWorkspace(studyId),
    ]);
    setState({
      ...passages,
      quality,
      exportCommand: workspace.exportCommand,
      exportBlockers: workspace.blockers.map((blocker) => blocker.code),
    });
  }, [studyId]);

  useEffect(() => {
    void refresh().catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : "Unable to load drafting workspace");
    });
  }, [refresh]);

  async function generate(section: Section) {
    setGenerating(section);
    setError(null);
    try {
      await protocolDraftingApi.generatePassage({ studyId, section });
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to generate passage");
    } finally {
      setGenerating(null);
    }
  }

  if (error) {
    return (
      <main className="workspace-shell">
        <h1>Drafting workspace unavailable</h1>
        <p role="alert">{error}</p>
      </main>
    );
  }
  if (!state) {
    return <main className="workspace-shell"><p role="status">Loading drafting workspace…</p></main>;
  }

  const passageApi: PassageApi = {
    reviewPassage: ({ passageId, action, expectedVersion, text, supportIds, rationale }) =>
      protocolDraftingApi.reviewPassage({
        studyId, passageId, action, expectedVersion, text, supportIds, rationale,
      }),
  };

  return (
    <main className="workspace-shell">
      <ProtocolNavigator passages={state.passages} />
      {sections.map(([section, label]) => {
        const passage = state.passages.find((item) => item.id === section || item.section === section.replaceAll("_", " "));
        return passage ? (
          <PassageEditor
            key={passage.id}
            passage={passage}
            api={passageApi}
            readOnly={state.readOnly}
            onUpdated={() => { void refresh().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to refresh passage")); }}
          />
        ) : (
          <section key={section} aria-labelledby={`${section}-heading`}>
            <h1 id={`${section}-heading`}>{label}</h1>
            <p>No saved passage has been generated for this section.</p>
            <button
              type="button"
              disabled={state.readOnly || generating !== null}
              onClick={() => void generate(section)}
            >
              Generate {label}
            </button>
          </section>
        );
      })}
      <Scorecard card={state.quality} />
      <ExportPanel
        studyId={studyId}
        exportCommand={state.exportCommand}
        state={{ blockers: state.exportBlockers, snapshotId: null, artifacts: [] } satisfies ExportState}
      />
    </main>
  );
}
