import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ModelExplorer } from "../../src/features/model/ModelExplorer";
import type { StudyModel } from "../../src/lib/types";

afterEach(cleanup);

const model: StudyModel = {
  facts: [
    {
      id: "fact-dose",
      label: "Dose",
      value: "10 mg once daily",
      status: "approved",
      version: "v3",
      provenance: ["Synopsis p. 4"],
      conflicts: [],
      affectedPassages: ["Treatment administration"],
      relationships: [{ label: "belongs to arm", target: "Arm A" }],
    },
    {
      id: "fact-endpoint",
      label: "Primary endpoint",
      value: "Change from baseline at Week 24",
      status: "conflict",
      version: "v2",
      provenance: ["Synopsis p. 6", "CSR extract p. 2"],
      conflicts: ["Endpoint wording differs across sources"],
      affectedPassages: ["Objectives", "Endpoints"],
      relationships: [{ label: "measured at", target: "Week 24" }],
    },
  ],
};

describe("ModelExplorer", () => {
  it("shows provenance, conflicts, affected passages, and keyboard-selectable facts", async () => {
    const user = userEvent.setup();

    render(<ModelExplorer model={model} />);

    assert.ok(screen.getByRole("tree", { name: "Canonical study facts" }));
    assert.ok(screen.getByText("Endpoint wording differs across sources"));
    assert.ok(screen.getByText("Affected passages: Objectives, Endpoints"));
    assert.ok(screen.getByText("Text alternative: Primary endpoint measured at Week 24"));

    await user.keyboard("{ArrowDown}");
    assert.equal(screen.getByTestId("selected-fact").textContent, "Primary endpoint");
  });
});
