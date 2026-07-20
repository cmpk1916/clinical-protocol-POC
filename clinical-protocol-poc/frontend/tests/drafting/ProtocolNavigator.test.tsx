import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";

import { ProtocolNavigator } from "../../src/features/drafting/ProtocolNavigator";
import type { DraftPassage } from "../../src/lib/types";

afterEach(cleanup);

const passages: DraftPassage[] = [
  {
    id: "synopsis", section: "synopsis", text: "Synthetic study.", status: "accepted", version: 1,
    stale: false, findings: [], evidence: [], guidance: [], impact: [],
  },
  {
    id: "design", section: "study design", text: "Draft design.", status: "valid", version: 1,
    stale: false, findings: [], evidence: [], guidance: [], impact: [],
  },
];

describe("ProtocolNavigator", () => {
  it("shows the number of saved sections", () => {
    render(<ProtocolNavigator passages={passages} />);

    assert.ok(screen.getByText("1 of 4 sections saved"));
    assert.ok(screen.getByText("objectives endpoints — missing"));
    assert.ok(screen.getByText("eligibility — missing"));
  });
});
