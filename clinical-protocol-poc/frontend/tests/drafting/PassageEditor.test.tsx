import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PassageEditor } from "../../src/features/drafting/PassageEditor";
import { Scorecard } from "../../src/features/quality/Scorecard";
import type { DraftPassage, PassageApi, QualityScorecard } from "../../src/lib/types";

afterEach(cleanup);

const blockedPassage: DraftPassage = {
  id: "passage-dose",
  section: "Treatment administration",
  text: "Participants receive 20 mg once daily.",
  status: "blocked",
  stale: false,
  findings: [{ code: "UNSUPPORTED_CONTENT", message: "Unsupported dose: 20 mg" }],
  evidence: ["Synopsis p. 4 supports 10 mg once daily"],
  guidance: ["Use approved facts only."],
  impact: ["Export blocked", "Traceability incomplete"],
};

const api: PassageApi = {
  async acceptPassage() {
    return { ok: true };
  },
  async validatePassage() {
    return {
      ok: false,
      findings: [{ code: "UNSUPPORTED_CONTENT", message: "Unsupported dose: 20 mg" }],
    };
  },
};

const scorecard: QualityScorecard = {
  disclaimer: "Dimension-level signal only; not readiness.",
  dimensions: [
    { name: "Traceability", status: "blocked", count: 2, findings: ["Missing endpoint evidence"] },
    { name: "Completeness", status: "warning", count: 1, findings: ["Eligibility needs review"] },
    { name: "Consistency", status: "pass", count: 0, findings: [] },
    { name: "Guidance coverage", status: "pass", count: 0, findings: [] },
    { name: "Staleness", status: "pass", count: 0, findings: [] },
    { name: "Export blockers", status: "blocked", count: 1, findings: ["Unsupported dose"] },
  ],
};

describe("PassageEditor", () => {
  it("prevents acceptance when a claim is unsupported", () => {
    render(<PassageEditor passage={blockedPassage} api={api} />);

    assert.ok(screen.getByText("Unsupported dose: 20 mg"));
    assert.equal(screen.getByRole("button", { name: "Accept passage" }).hasAttribute("disabled"), true);
  });

  it("preserves edited text when validation returns findings", async () => {
    const user = userEvent.setup();
    render(<PassageEditor passage={{ ...blockedPassage, text: "Draft" }} api={api} />);

    await user.clear(screen.getByLabelText("Passage text"));
    await user.type(screen.getByLabelText("Passage text"), "Participants receive 20 mg.");
    await user.click(screen.getByRole("button", { name: "Validate passage" }));

    assert.equal(screen.getByLabelText("Passage text").textContent, "Participants receive 20 mg.");
    assert.ok(screen.getByText("Unsupported dose: 20 mg"));
  });
});

describe("Scorecard", () => {
  it("shows dimensions without an overall percentage", () => {
    render(<Scorecard card={scorecard} />);

    assert.equal(screen.queryByText(/overall/i), null);
    assert.ok(screen.getByText("Traceability"));
    assert.ok(screen.getByText("Dimension-level signal only; not readiness."));
  });
});
