import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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

  it("prevents re-accepting a passage that is already accepted", () => {
    render(<PassageEditor passage={{ ...blockedPassage, status: "accepted", findings: [] }} api={api} />);

    assert.equal(screen.getByRole("button", { name: "Accept passage" }).hasAttribute("disabled"), true);
  });

  it("prevents accepting a draft until it is regenerated against current supports", () => {
    render(
      <PassageEditor
        passage={{ ...blockedPassage, status: "draft", findings: [] }}
        api={api}
      />,
    );

    assert.equal(
      screen.getByRole("button", { name: "Accept passage" }).hasAttribute("disabled"),
      true,
    );
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

  it("sends an optimistic versioned accept command and refreshes from the authoritative passage", async () => {
    const user = userEvent.setup();
    const calls: unknown[] = [];
    const ready: DraftPassage = {
      ...blockedPassage,
      status: "valid",
      findings: [],
      text: "Participants receive 10 mg once daily.",
    };
    const commandApi = {
      ...api,
      async reviewPassage(input: unknown) {
        calls.push(input);
        return { ...ready, status: "accepted" as const };
      },
    };
    let refreshed: DraftPassage | null = null;

    render(<PassageEditor passage={{ ...ready, version: 3 }} api={commandApi} onUpdated={(passage) => { refreshed = passage; }} />);
    await user.click(screen.getByRole("button", { name: "Accept passage" }));

    assert.deepEqual(calls, [{ passageId: "passage-dose", action: "accept", expectedVersion: 3 }]);
    const authoritativePassage = refreshed as DraftPassage | null;
    assert.equal(authoritativePassage?.status, "accepted");
  });

  it("keeps the passage busy until the authoritative parent refresh completes", async () => {
    const user = userEvent.setup();
    let resolveRefresh: (() => void) | undefined;
    const ready: DraftPassage = {
      ...blockedPassage,
      status: "valid",
      findings: [],
      text: "Participants receive 10 mg once daily.",
      version: 3,
    };
    const commandApi = {
      ...api,
      async reviewPassage() {
        return { ...ready, status: "accepted" as const };
      },
    };

    render(
      <PassageEditor
        passage={ready}
        api={commandApi}
        onUpdated={() => new Promise<void>((resolve) => { resolveRefresh = resolve; })}
      />,
    );
    const acceptance = user.click(screen.getByRole("button", { name: "Accept passage" }));

    assert.equal((await screen.findByRole("status")).textContent, "Saving passage review…");
    assert.ok(resolveRefresh);
    resolveRefresh();
    await acceptance;
    await waitFor(() => assert.equal(screen.queryByRole("status"), null));
  });

  it("keeps archived passage review viewable but disables every mutation", () => {
    render(<PassageEditor passage={{ ...blockedPassage, version: 1 }} api={api} readOnly />);

    for (const name of ["Validate passage", "Accept passage", "Edit passage", "Reject passage", "Regenerate passage"]) {
      assert.equal(screen.getByRole("button", { name }).hasAttribute("disabled"), true);
    }
    assert.ok(screen.getByText(/archived passage review is read-only/i));
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
