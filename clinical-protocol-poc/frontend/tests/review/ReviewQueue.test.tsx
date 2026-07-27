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
          evidenceText: "Intervention: Example drug 10 mg once daily",
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
    return { blockers: [], items: [] };
  },
  async reviewFact() {
    return { blockers: [], items: [] };
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
    assert.ok(screen.getByText("Intervention: Example drug 10 mg once daily"));
  });

  it("refreshes the queue from the authoritative approval result", async () => {
    const user = userEvent.setup();
    render(<ReviewQueue studyId="study-1" api={criticalFactApi} />);
    await screen.findByRole("button", { name: "Approve fact" });
    await user.click(screen.getByRole("button", { name: "Approve fact" }));
    await user.click(screen.getByLabelText("I explicitly confirm this critical fact"));
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));
    assert.ok(await screen.findByText("All candidate facts have been reviewed."));
  });

  it("locks other critical reviews while an approval refresh is in flight", async () => {
    let resolveApproval: ((payload: Awaited<ReturnType<ReviewApi["approveFact"]>>) => void) | undefined;
    const secondCriticalFact = {
      ...(await criticalFactApi.getReviewQueue("study-1")).items[0]!,
      id: "fact-eligibility",
      label: "Eligibility",
      versionToken: "v-eligibility-1",
    };
    const api: ReviewApi = {
      ...criticalFactApi,
      async getReviewQueue() {
        const payload = await criticalFactApi.getReviewQueue("study-1");
        return { ...payload, items: [payload.items[0]!, secondCriticalFact] };
      },
      approveFact() {
        return new Promise((resolve) => {
          resolveApproval = resolve;
        });
      },
    };
    const user = userEvent.setup();
    render(<ReviewQueue studyId="study-1" api={api} />);

    const approvalButtons = await screen.findAllByRole("button", { name: "Approve fact" });
    await user.click(approvalButtons[0]!);
    await user.click(screen.getByLabelText("I explicitly confirm this critical fact"));
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));

    assert.equal(approvalButtons[1]!.hasAttribute("disabled"), true);

    resolveApproval?.({ blockers: [], items: [secondCriticalFact] });
    assert.ok(await screen.findByRole("button", { name: "Approve fact" }));
  });

  it("keeps archived evidence viewable while disabling review actions", async () => {
    const archivedApi: ReviewApi = {
      ...criticalFactApi,
      async getReviewQueue(studyId) {
        return { ...(await criticalFactApi.getReviewQueue(studyId)), readOnly: true };
      },
    };
    render(<ReviewQueue studyId="study-1" api={archivedApi} />);
    assert.ok(await screen.findByText(/archived review is read-only/i));
    assert.ok(screen.getByText("Intervention: Example drug 10 mg once daily"));
    assert.equal(screen.getByRole("button", { name: "Approve fact" }).hasAttribute("disabled"), true);
  });

  it("shows deferred facts and resumes them through an authoritative refresh", async () => {
    const calls: Array<{ action: string; rationale: string }> = [];
    const api: ReviewApi = {
      ...criticalFactApi,
      async getReviewQueue() {
        const payload = await criticalFactApi.getReviewQueue("study-1");
        return { ...payload, items: [{ ...payload.items[0]!, status: "deferred" }] };
      },
      async reviewFact(input) {
        calls.push({ action: input.action, rationale: input.rationale });
        return { blockers: [], items: [] };
      },
    };
    const user = userEvent.setup();
    render(<ReviewQueue studyId="study-1" api={api} />);

    await user.click(await screen.findByRole("button", { name: "Resume review" }));

    assert.deepEqual(calls, [{ action: "resume", rationale: "Resumed during guided review." }]);
    assert.ok(await screen.findByText("All candidate facts have been reviewed."));
  });

  it("requires a rationale to resolve conflicts and refreshes from the server", async () => {
    const calls: Array<{ action: string; rationale: string }> = [];
    const api: ReviewApi = {
      ...criticalFactApi,
      async getReviewQueue() {
        const payload = await criticalFactApi.getReviewQueue("study-1");
        return { ...payload, items: [{ ...payload.items[0]!, status: "conflict" }] };
      },
      async reviewFact(input) {
        calls.push({ action: input.action, rationale: input.rationale });
        return { blockers: [], items: [] };
      },
    };
    const user = userEvent.setup();
    render(<ReviewQueue studyId="study-1" api={api} />);

    const resolve = await screen.findByRole("button", { name: "Resolve conflict" });
    assert.equal(resolve.hasAttribute("disabled"), true);
    await user.type(screen.getByLabelText("Conflict resolution rationale"), "Use exact synopsis evidence");
    await user.click(resolve);

    assert.deepEqual(calls, [{ action: "resolve_conflict", rationale: "Use exact synopsis evidence" }]);
    assert.ok(await screen.findByText("All candidate facts have been reviewed."));
  });

  it("fails closed and disables mutations when exact evidence cannot be verified", async () => {
    const api: ReviewApi = {
      ...criticalFactApi,
      async getReviewQueue() {
        const payload = await criticalFactApi.getReviewQueue("study-1");
        return {
          ...payload,
          items: [{
            ...payload.items[0]!,
            evidenceValid: false,
            evidenceLocation: "",
            evidenceText: "",
          }],
        };
      },
    };
    render(<ReviewQueue studyId="study-1" api={api} />);

    assert.ok(await screen.findByRole("alert", { name: "Exact evidence verification failed" }));
    assert.equal(screen.queryByText(/unavailable/i), null);
    for (const name of ["Approve fact", "Reject fact", "Defer fact"]) {
      assert.equal(screen.getByRole("button", { name }).hasAttribute("disabled"), true);
    }
  });

  it("keeps a candidate with no current version visible as a blocked review item", async () => {
    const api: ReviewApi = {
      ...criticalFactApi,
      async getReviewQueue() {
        const payload = await criticalFactApi.getReviewQueue("study-1");
        return {
          ...payload,
          items: [{
            ...payload.items[0]!,
            candidateValue: "Unavailable",
            evidenceValid: false,
            evidenceLocation: "",
            evidenceText: "",
          }],
        };
      },
    };
    render(<ReviewQueue studyId="study-1" api={api} />);

    assert.ok(await screen.findByText("Investigational product dose"));
    assert.ok(screen.getByRole("alert", { name: "Exact evidence verification failed" }));
    assert.equal(screen.queryByText("All candidate facts have been reviewed."), null);
    for (const name of ["Approve fact", "Reject fact", "Defer fact"]) {
      assert.equal(screen.getByRole("button", { name }).hasAttribute("disabled"), true);
    }
  });
});
