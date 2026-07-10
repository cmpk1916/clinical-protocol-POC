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
            { name: "protocol.docx", sha256: "docxhash", snapshotId: "snapshot-123" },
            { name: "traceability.csv", sha256: "csvhash", snapshotId: "snapshot-123" },
            { name: "scorecard.html", sha256: "htmlhash", snapshotId: "snapshot-123" },
          ],
        };
      },
    };

    render(<ExportPanel studyId="study-1" state={{ blockers: [], snapshotId: null, artifacts: [] }} api={api} />);
    await user.click(screen.getByRole("button", { name: "Create export" }));

    assert.equal(screen.getByTestId("snapshot-id").textContent, "snapshot-123");
    assert.ok(screen.getByText("protocol.docx"));
    assert.ok(screen.getByText("docxhash"));
    assert.match(screen.getByTestId("artifact-snapshot-ids").textContent ?? "", /snapshot-123/);
  });
});
