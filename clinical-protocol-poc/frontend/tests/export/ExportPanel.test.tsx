import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ExportPanel } from "../../src/features/export/ExportPanel";
import type { ExportApi, ExportState } from "../../src/lib/types";

afterEach(cleanup);

const blockedState: ExportState = {
  blockers: ["Unsupported dose claim must be resolved"],
  snapshotId: null,
  artifacts: [],
};

describe("ExportPanel", () => {
  it("shows every blocker and keeps export disabled until the server gate is clear", () => {
    render(<ExportPanel studyId="study-1" state={blockedState} api={{ createExport: async () => blockedState }} />);

    assert.ok(screen.getByRole("alert"));
    assert.ok(screen.getByText("Unsupported dose claim must be resolved"));
    assert.equal(screen.getByRole("button", { name: "Create export" }).hasAttribute("disabled"), true);
  });

  it("shows artifact names, hashes, and the shared snapshot after export succeeds", async () => {
    const user = userEvent.setup();
    const api: ExportApi = {
      async createExport() {
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

    render(<ExportPanel studyId="study-1" state={{ blockers: [], snapshotId: null, artifacts: [] }} api={api} />);
    await user.click(screen.getByRole("button", { name: "Create export" }));

    assert.equal(screen.getByTestId("snapshot-id").textContent, "snapshot-123");
    assert.ok(screen.getByText("docxhash"));
    assert.equal(screen.getByRole("link", { name: "Download protocol.docx" }).getAttribute("href"), "/api/artifacts/docx");
    assert.match(screen.getByTestId("artifact-snapshot-ids").textContent ?? "", /snapshot-123/);
  });
});
