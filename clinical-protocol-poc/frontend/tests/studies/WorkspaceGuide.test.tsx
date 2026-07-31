import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { WorkspaceGuide } from "../../src/features/studies/WorkspaceGuide";
import {
  toWorkspaceSummary,
  type WorkspaceApi,
  type WorkspacePayload,
  type WorkspaceSummary,
} from "../../src/lib/api";

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
    blockers: [{
      code: "SYNOPSIS_DOSE_MISSING",
      message: "Intervention values must include an N mg dose and once daily frequency.",
      affectedArea: "arms_interventions",
      blockingReason: "Synopsis processing cannot succeed until the source content is corrected.",
    }],
    inputs: {
      synopsis: { role: "synopsis", versionId: "synopsis-v1", version: 1, filename: "synopsis.docx", conformanceStatus: "conforming" },
      template: { role: "template", versionId: "template-v1", version: 1, filename: "template.docx", conformanceStatus: "conforming" },
    },
    processing: { attemptId: "attempt-failed", status: "failed", findings: [] },
    nextAction: { kind: "upload_synopsis", label: "Upload corrected synopsis", targetId: null, href: null },
    exportCommand: null,
    ...overrides,
  };
}

describe("WorkspaceGuide", () => {
  it("shows processing findings and retry then replaces state from the authoritative response", async () => {
    const technicalFailure = summary({
      blockers: [{
        code: "PROCESSING_FAILED",
        message: "Synopsis processing did not complete.",
        affectedArea: "synopsis",
        blockingReason: "Synopsis processing did not complete, so downstream review and export remain blocked.",
      }],
      nextAction: {
        kind: "retry_processing",
        label: "Retry synopsis processing",
        targetId: "attempt-failed",
        href: null,
      },
    });
    const refreshed = summary({
      step: "fact_review",
      blockers: [],
      processing: { attemptId: "attempt-new", status: "succeeded", findings: [] },
      counts: { candidateFacts: 7, conflictedFacts: 0, approvedFacts: 0, acceptedPassages: 0, totalPassages: 0, exports: 0 },
      nextAction: { kind: "review_facts", label: "Review 7 candidate facts", targetId: null, href: "/studies/study-1/review" },
    });
    let retries = 0;
    const api: WorkspaceApi = {
      async getWorkspace() { return technicalFailure; },
      async processSynopsis() { throw new Error("not used"); },
      async retryProcessing(studyId, attemptId) {
        assert.equal(studyId, "study-1");
        assert.equal(attemptId, "attempt-failed");
        retries += 1;
        return refreshed;
      },
      async uploadInput() { throw new Error("not used"); },
    };
    render(<WorkspaceGuide initialSummary={technicalFailure} api={api} />);

    assert.ok(screen.getByText("Synopsis processing did not complete."));
    await userEvent.click(screen.getByRole("button", { name: "Retry synopsis processing" }));

    assert.equal(retries, 1);
    assert.ok(await screen.findByRole("link", { name: "Review 7 candidate facts" }));
    assert.match(document.body.textContent ?? "", /7 candidate facts/);
  });

  it("explains a source correction and keeps the matching upload available", () => {
    render(<WorkspaceGuide initialSummary={summary()} />);

    const finding = screen.getByText(
      "Intervention values must include an N mg dose and once daily frequency.",
    ).closest("li");
    assert.ok(finding);
    assert.match(finding.textContent ?? "", /Affected area: arms interventions/);
    assert.match(
      finding.textContent ?? "",
      /cannot succeed until the source content is corrected/i,
    );
    assert.ok(screen.getByRole("heading", { name: "Upload corrected synopsis" }));
    assert.equal(screen.getByLabelText("Synopsis DOCX").hasAttribute("disabled"), false);
    assert.equal(
      screen.queryByRole("button", { name: /retry synopsis processing/i }),
      null,
    );
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

describe("toWorkspaceSummary", () => {
  it("maps blocker details once for workspace and processing state", () => {
    const blocker = {
      code: "SYNOPSIS_DOSE_MISSING",
      message: "A dose is required.",
      affected_area: "arms_interventions",
      blocking_reason: "Correct the source synopsis.",
    };
    const payload = {
      study: { id: "study-1", name: "Synthetic Study", lifecycle: "active", version: 1 },
      step: "processing",
      read_only: false,
      steps: [],
      counts: {
        candidate_facts: 0,
        conflicted_facts: 0,
        approved_facts: 0,
        accepted_passages: 0,
        total_passages: 0,
        stale_passages: 0,
        blocked_passages: 0,
        rejected_passages: 0,
        exports: 0,
      },
      blockers: [blocker],
      inputs: { synopsis: null, template: null },
      processing: {
        attempt_id: "attempt-1",
        status: "failed",
        findings: [blocker],
      },
      next_action: {
        kind: "upload_synopsis",
        label: "Upload corrected synopsis",
        target_id: null,
        href: null,
      },
      export_command: null,
    } as unknown as WorkspacePayload;

    const mapped = toWorkspaceSummary(payload);
    const expected = {
      code: "SYNOPSIS_DOSE_MISSING",
      message: "A dose is required.",
      affectedArea: "arms_interventions",
      blockingReason: "Correct the source synopsis.",
    };

    assert.deepEqual(mapped.blockers, [expected]);
    assert.deepEqual(mapped.processing?.findings, [expected]);
  });
});
