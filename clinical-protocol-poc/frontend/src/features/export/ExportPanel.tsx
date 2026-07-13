"use client";

import React from "react";
import { useState } from "react";

import { protocolExportApi } from "../../lib/api";
import type { ExportApi, ExportState } from "../../lib/types";

export function ExportPanel({
  studyId,
  state,
  api = protocolExportApi,
}: Readonly<{ studyId: string; state: ExportState; api?: ExportApi }>) {
  const [exportState, setExportState] = useState(state);
  const blocked = exportState.blockers.length > 0;

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
      <button
        type="button"
        disabled={blocked}
        onClick={async () => setExportState(await api.createExport(studyId))}
      >
        Create export
      </button>
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
