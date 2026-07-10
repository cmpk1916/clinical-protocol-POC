import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ReviewQueue } from "../../src/features/review/ReviewQueue";
import type { ReviewApi } from "../../src/lib/api";

afterEach(cleanup);

const criticalFactApi: ReviewApi = {
  async getReviewQueue() {
    return {
      blockers: ["Export blocked: critical dose fact requires review"],
      items: [
        {
          id: "fact-dose",
          label: "Investigational product dose",
          category: "Intervention",
          candidateValue: "10 mg once daily",
          currentValue: "Unapproved",
          evidenceLocation: "Synopsis p. 4, Intervention paragraph 2",
          confidence: 0.91,
          downstreamImpact: ["Draft dose passage", "Traceability table", "Export gate"],
          isCritical: true,
          versionToken: "v-dose-3",
          status: "needs_review",
        },
      ],
    };
  },
  async approveFact() {
    return { ok: true };
  },
};

describe("ReviewQueue", () => {
  it("keeps blockers visible and requires confirmation for a critical fact", async () => {
    const user = userEvent.setup();

    render(<ReviewQueue studyId="study-1" api={criticalFactApi} />);

    assert.match((await screen.findByRole("alert")).textContent ?? "", /Export blocked/);
    await user.click(screen.getByRole("button", { name: "Approve fact" }));

    const confirmation = screen.getByLabelText("I explicitly confirm this critical fact");
    assert.equal(confirmation.hasAttribute("required"), true);
    assert.equal(document.activeElement, confirmation);
  });
});
