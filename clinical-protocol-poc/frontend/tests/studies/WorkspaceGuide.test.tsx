import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { WorkspaceGuide } from "../../src/features/studies/WorkspaceGuide";
import type { WorkspaceApi, WorkspaceSummary } from "../../src/lib/api";

afterEach(cleanup);

function summary(overrides: Partial<WorkspaceSummary> = {}): WorkspaceSummary {
  return {
    study: { id: "study-1", name: "Synthetic Study", lifecycle: "active", version: 1 },
    step: "processing",
    readOnly: false,
    steps: [
      { key: "inputs", label: "Inputs", status: "complete" },
      { key: "processing", label: "Processing", status: "current" },
      { key: "fact_review", label: "Fact review", status: "upcoming" },
      { key: "passage_review", label: "Passage review", status: "upcoming" },
      { key: "export", label: "Export", status: "upcoming" },
    ],
    counts: { candidateFacts: 0, conflictedFacts: 0, approvedFacts: 0, acceptedPassages: 0, totalPassages: 0, exports: 0 },
    blockers: [{ code: "SYNOPSIS_DOSE_MISSING", message: "Dose and frequency are required." }],
    inputs: {
      synopsis: { role: "synopsis", versionId: "synopsis-v1", version: 1, filename: "synopsis.docx", conformanceStatus: "conforming" },
      template: { role: "template", versionId: "template-v1", version: 1, filename: "template.docx", conformanceStatus: "conforming" },
    },
    processing: { attemptId: "attempt-failed", status: "failed", findings: [] },
    nextAction: { kind: "retry_processing", label: "Retry synopsis processing", targetId: "attempt-failed", href: null },
    ...overrides,
  };
}

describe("WorkspaceGuide", () => {
  it("shows processing findings and retry then replaces state from the authoritative response", async () => {
    const refreshed = summary({
      step: "fact_review",
      blockers: [],
      processing: { attemptId: "attempt-new", status: "succeeded", findings: [] },
      counts: { candidateFacts: 7, conflictedFacts: 0, approvedFacts: 0, acceptedPassages: 0, totalPassages: 0, exports: 0 },
      nextAction: { kind: "review_facts", label: "Review 7 candidate facts", targetId: null, href: "/studies/study-1/review" },
    });
    let retries = 0;
    const api: WorkspaceApi = {
      async getWorkspace() { return summary(); },
      async processSynopsis() { throw new Error("not used"); },
      async retryProcessing(studyId, attemptId) {
        assert.equal(studyId, "study-1");
        assert.equal(attemptId, "attempt-failed");
        retries += 1;
        return refreshed;
      },
      async uploadInput() { throw new Error("not used"); },
    };
    render(<WorkspaceGuide initialSummary={summary()} api={api} />);

    assert.ok(screen.getByText("Dose and frequency are required."));
    await userEvent.click(screen.getByRole("button", { name: "Retry synopsis processing" }));

    assert.equal(retries, 1);
    assert.ok(await screen.findByRole("link", { name: "Review 7 candidate facts" }));
    assert.match(document.body.textContent ?? "", /7 candidate facts/);
  });

  it("keeps archived workspaces viewable and disables input mutation", () => {
    render(
      <WorkspaceGuide
        initialSummary={summary({
          study: { id: "study-1", name: "Archived Study", lifecycle: "archived", version: 2 },
          step: "archived",
          readOnly: true,
          nextAction: { kind: "restore_study", label: "Restore from the study dashboard", targetId: null, href: "/" },
        })}
      />,
    );
    assert.ok(screen.getByText(/read-only/i));
    assert.equal(screen.getByLabelText("Synopsis DOCX").hasAttribute("disabled"), true);
    assert.ok(screen.getByText("synopsis.docx"));
  });
});
