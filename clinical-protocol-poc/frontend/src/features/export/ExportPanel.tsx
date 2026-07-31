"use client";

import React from "react";
import { useEffect, useState } from "react";

import { protocolExportApi } from "../../lib/api";
import type { ExportApi, ExportCommand, ExportState } from "../../lib/types";

export function ExportPanel({
  studyId,
  state,
  exportCommand,
  api = protocolExportApi,
}: Readonly<{
  studyId: string;
  state: ExportState;
  exportCommand: ExportCommand | null;
  api?: ExportApi;
}>) {
  const [exportState, setExportState] = useState(state);
  useEffect(() => {
    setExportState(state);
  }, [state, exportCommand, studyId]);
  const hasSavedExport = exportState.snapshotId !== null;
  const blocked = !hasSavedExport
    && (exportState.blockers.length > 0 || exportCommand === null);

  async function createExport() {
    if (exportCommand === null) return;
    try {
      setExportState(await api.createExport(studyId, exportCommand));
    } catch (cause) {
      setExportState({
        blockers: [cause instanceof Error ? cause.message : "EXPORT_FAILED"],
        snapshotId: null,
        artifacts: [],
      });
    }
  }

  return (
    <section aria-labelledby="export-heading">
      <h2 id="export-heading">Export</h2>
      {blocked ? (
        <div role="alert">
          <p>Export blocked by server-side gate.</p>
          <ul>
            {exportState.blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {!hasSavedExport ? (
        <button
          type="button"
          disabled={blocked}
          onClick={() => void createExport()}
        >
          Create export
        </button>
      ) : null}
      {exportState.snapshotId ? (
        <section aria-label="Export artifacts">
          <h3>Artifacts</h3>
          <p data-testid="snapshot-id">{exportState.snapshotId}</p>
          <ul data-testid="artifact-snapshot-ids">
            {exportState.artifacts.map((artifact) => (
              <li key={artifact.name}>
                <a href={artifact.downloadUrl} download={artifact.name}>
                  Download {artifact.name}
                </a>{" "}
                · <span>{artifact.sha256}</span> · <span>{artifact.snapshotId}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
