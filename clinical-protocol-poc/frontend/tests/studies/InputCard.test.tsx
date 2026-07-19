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
});
