import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { InputCard } from "../../src/features/studies/InputCard";
import type { InputApi, WorkspaceSummary } from "../../src/lib/api";

afterEach(cleanup);

const workspace = { step: "inputs" } as WorkspaceSummary;

describe("InputCard", () => {
  it("prompts for a missing synopsis and lists validation findings", async () => {
    const api: InputApi = {
      async uploadInput() {
        return {
          outcome: {
            status: "conformance_failed",
            findings: [
              { code: "SYNOPSIS_ENDPOINTS_MISSING", field: "endpoints", message: "Endpoints are required." },
              { code: "SYNOPSIS_DOSE_MISSING", field: "dose", message: "Dose and frequency are required." },
            ],
          },
          workspace,
        };
      },
    };
    render(
      <InputCard
        studyId="study-1"
        role="synopsis"
        input={null}
        api={api}
        disabled={false}
        onWorkspace={() => undefined}
      />,
    );

    assert.match(screen.getByText(/Upload a supported synopsis DOCX/i).textContent ?? "", /DOCX/);
    const file = new File(["synthetic"], "synopsis.docx", { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    await userEvent.upload(screen.getByLabelText("Synopsis DOCX"), file);
    await userEvent.click(screen.getByRole("button", { name: "Upload synopsis" }));

    assert.ok(await screen.findByText("Endpoints are required."));
    assert.ok(screen.getByText("Dose and frequency are required."));
  });

  it("shows the authoritative current file descriptor", () => {
    render(
      <InputCard
        studyId="study-1"
        role="template"
        input={{
          role: "template",
          versionId: "version-a",
          version: 2,
          filename: "protocol-template.docx",
          conformanceStatus: "conforming",
        }}
        disabled
        onWorkspace={() => undefined}
      />,
    );
    assert.match(document.body.textContent ?? "", /protocol-template\.docx/);
    assert.match(document.body.textContent ?? "", /Version 2/);
    assert.equal(screen.getByLabelText("Template DOCX").hasAttribute("disabled"), true);
  });

  it("shows versioned effects before confirming a replacement", async () => {
    const user = userEvent.setup();
    let confirmed = false;
    const api: InputApi = {
      async uploadInput() {
        return {
          outcome: { status: "replacement_confirmation_required", findings: [], version_id: "synopsis-v2" },
          workspace: { ...workspace, study: { id: "study-1", version: 3 } } as WorkspaceSummary,
        };
      },
      async previewReplacement() {
        return {
          role: "synopsis",
          current_version_id: "synopsis-v1",
          current_filename: "synopsis-v1.docx",
          current_version: 1,
          proposed_version_id: "synopsis-v2",
          proposed_filename: "synopsis-v2.docx",
          proposed_version: 2,
          conformance_status: "conforming",
          effects: ["supersede_current_facts", "invalidate_dependent_passages", "fact_review_required"],
        };
      },
      async confirmReplacement() {
        confirmed = true;
        return workspace;
      },
    };
    render(
      <InputCard
        studyId="study-1"
        role="synopsis"
        input={{ role: "synopsis", versionId: "synopsis-v1", version: 1, filename: "synopsis-v1.docx", conformanceStatus: "conforming" }}
        api={api}
        disabled={false}
        onWorkspace={() => undefined}
      />,
    );

    await user.upload(screen.getByLabelText("Synopsis DOCX"), new File(["synthetic"], "synopsis-v2.docx"));
    await user.click(screen.getByRole("button", { name: "Upload synopsis" }));

    assert.equal((await screen.findAllByText("synopsis-v1.docx")).length, 2);
    assert.ok(screen.getByText("synopsis-v2.docx"));
    assert.ok(screen.getByText("supersede current facts"));
    await user.click(screen.getByRole("button", { name: "Confirm replacement" }));
    assert.equal(confirmed, true);
  });

  it("refreshes after a replacement conflict and displays the stale-window message", async () => {
    const user = userEvent.setup();
    let refreshed = false;
    const api: InputApi = {
      async uploadInput() {
        return {
          outcome: { status: "replacement_confirmation_required", findings: [], version_id: "synopsis-v2" },
          workspace: { ...workspace, study: { id: "study-1", version: 3 } } as WorkspaceSummary,
        };
      },
      async previewReplacement() {
        return {
          role: "synopsis", current_version_id: "synopsis-v1", current_filename: "synopsis-v1.docx", current_version: 1,
          proposed_version_id: "synopsis-v2", proposed_filename: "synopsis-v2.docx", proposed_version: 2,
          conformance_status: "conforming", effects: ["fact_review_required"],
        };
      },
      async confirmReplacement() { throw new Error("STUDY_VERSION_CONFLICT"); },
      async getWorkspace() { refreshed = true; return workspace; },
    };
    render(<InputCard studyId="study-1" role="synopsis" input={{ role: "synopsis", versionId: "synopsis-v1", version: 1, filename: "synopsis-v1.docx", conformanceStatus: "conforming" }} api={api} disabled={false} onWorkspace={() => undefined} />);

    await user.upload(screen.getByLabelText("Synopsis DOCX"), new File(["synthetic"], "synopsis-v2.docx"));
    await user.click(screen.getByRole("button", { name: "Upload synopsis" }));
    await user.click(await screen.findByRole("button", { name: "Confirm replacement" }));

    assert.ok(await screen.findByText("The study changed in another window. Review the latest version before trying again."));
    assert.equal(refreshed, true);
  });
});
