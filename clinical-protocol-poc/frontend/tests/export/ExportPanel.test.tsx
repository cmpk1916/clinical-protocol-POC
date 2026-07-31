import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ExportPanel } from "../../src/features/export/ExportPanel";
import { protocolExportApi } from "../../src/lib/api";
import type { ExportApi, ExportCommand, ExportState } from "../../src/lib/types";

afterEach(cleanup);

const blockedState: ExportState = {
  blockers: ["Unsupported dose claim must be resolved"],
  snapshotId: null,
  artifacts: [],
};

const exportCommand: ExportCommand = {
  expectedStudyVersion: 3,
  templateVersionId: "template-v3",
  templateHash: "a".repeat(64),
};

describe("ExportPanel", () => {
  it("shows every blocker and keeps export disabled until the server gate is clear", () => {
    render(<ExportPanel studyId="study-1" state={blockedState} exportCommand={exportCommand} api={{ loadLatest: async () => blockedState, createExport: async () => blockedState }} />);

    assert.ok(screen.getByRole("alert"));
    assert.ok(screen.getByText("Unsupported dose claim must be resolved"));
    assert.equal(screen.getByRole("button", { name: "Create export" }).hasAttribute("disabled"), true);
  });

  it("shows artifact names, hashes, and the shared snapshot after export succeeds", async () => {
    const user = userEvent.setup();
    const api: ExportApi = {
      async loadLatest() {
        return { blockers: [], snapshotId: null, artifacts: [] };
      },
      async createExport(_studyId, command) {
        assert.deepEqual(command, exportCommand);
        return {
          blockers: [],
          snapshotId: "snapshot-123",
          artifacts: [
            { id: "docx", name: "protocol.docx", mediaType: "application/docx", sha256: "docxhash", snapshotId: "snapshot-123", downloadUrl: "/api/artifacts/docx" },
            { id: "csv", name: "traceability.csv", mediaType: "text/csv", sha256: "csvhash", snapshotId: "snapshot-123", downloadUrl: "/api/artifacts/csv" },
            { id: "html", name: "scorecard.html", mediaType: "text/html", sha256: "htmlhash", snapshotId: "snapshot-123", downloadUrl: "/api/artifacts/html" },
          ],
        };
      },
    };

    render(<ExportPanel studyId="study-1" state={{ blockers: [], snapshotId: null, artifacts: [] }} exportCommand={exportCommand} api={api} />);
    await user.click(screen.getByRole("button", { name: "Create export" }));

    assert.equal(screen.getByTestId("snapshot-id").textContent, "snapshot-123");
    assert.ok(screen.getByText("docxhash"));
    assert.equal(screen.getByRole("link", { name: "Download protocol.docx" }).getAttribute("href"), "/api/artifacts/docx");
    assert.match(screen.getByTestId("artifact-snapshot-ids").textContent ?? "", /snapshot-123/);
  });

  it("shows a saved export without offering duplicate creation", () => {
    render(
      <ExportPanel
        studyId="study-1"
        exportCommand={exportCommand}
        state={{
          blockers: [],
          snapshotId: "snapshot-saved",
          artifacts: [{
            id: "docx",
            name: "protocol.docx",
            mediaType: "application/docx",
            sha256: "a".repeat(64),
            snapshotId: "snapshot-saved",
            downloadUrl: "/api/local/export-artifacts/docx",
          }],
        }}
      />,
    );

    assert.ok(screen.getByRole("link", { name: "Download protocol.docx" }));
    assert.equal(screen.queryByRole("button", { name: "Create export" }), null);
  });

  it("adopts refreshed authority state and clears prior artifacts on rerender", () => {
    const view = render(
      <ExportPanel
        studyId="study-1"
        exportCommand={exportCommand}
        state={{
          blockers: [], snapshotId: "snapshot-old",
          artifacts: [{ id: "old", name: "protocol.docx", mediaType: "application/docx", sha256: "old", snapshotId: "snapshot-old", downloadUrl: "/old" }],
        }}
      />,
    );
    assert.ok(screen.getByRole("link", { name: "Download protocol.docx" }));

    view.rerender(
      <ExportPanel
        studyId="study-2"
        exportCommand={null}
        state={{ blockers: ["STUDY_ARCHIVED"], snapshotId: null, artifacts: [] }}
      />,
    );

    assert.ok(screen.getByText("STUDY_ARCHIVED"));
    assert.equal(screen.queryByRole("link", { name: "Download protocol.docx" }), null);
    assert.equal(screen.getByRole("button", { name: "Create export" }).hasAttribute("disabled"), true);
  });

  it("posts the workspace command through the local proxy and rewrites artifact downloads", async () => {
    const originalFetch = globalThis.fetch;
    let request: { url: string; init?: RequestInit } | null = null;
    globalThis.fetch = async (url, init) => {
      request = { url: String(url), init };
      return new Response(JSON.stringify({
        blockers: [],
        snapshotId: "snapshot-123",
        artifacts: [{ id: "docx", name: "protocol.docx", mediaType: "application/docx", sha256: "docxhash", snapshotId: "snapshot-123", downloadUrl: "/api/export-artifacts/docx" }],
      }), { status: 201, headers: { "Content-Type": "application/json" } });
    };
    try {
      const result = await protocolExportApi.createExport("study-1", exportCommand);

      assert.deepEqual(request, {
        url: "/api/local/studies/study-1/exports",
        init: {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(exportCommand),
        },
      });
      assert.equal(result.artifacts[0]?.downloadUrl, "/api/local/export-artifacts/docx");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("loads the latest export through the local proxy and rewrites downloads", async () => {
    const originalFetch = globalThis.fetch;
    let request: { url: string; init?: RequestInit } | null = null;
    globalThis.fetch = async (url, init) => {
      request = { url: String(url), init };
      return Response.json({
        blockers: [],
        snapshotId: "snapshot-saved",
        artifacts: [{
          id: "docx",
          name: "protocol.docx",
          mediaType: "application/docx",
          sha256: "a".repeat(64),
          snapshotId: "snapshot-saved",
          downloadUrl: "/api/export-artifacts/docx",
        }],
      });
    };
    try {
      const result = await protocolExportApi.loadLatest("study-1");

      assert.deepEqual(request, {
        url: "/api/local/studies/study-1/exports/latest",
        init: undefined,
      });
      assert.equal(result.artifacts[0]?.downloadUrl, "/api/local/export-artifacts/docx");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
