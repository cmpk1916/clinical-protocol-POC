import assert from "node:assert/strict";
import test from "node:test";

import { protocolDraftingApi } from "../../src/lib/api";

test("maps quality finding_codes into scorecard findings", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    dimensions: {
      completeness: {
        status: "blocked",
        passed_count: 3,
        blocker_codes: [],
        finding_codes: ["REQUIRED_PLACEHOLDER"],
      },
    },
    blockers: [],
  }));

  try {
    const scorecard = await protocolDraftingApi.getQuality("study-1");

    assert.deepEqual(scorecard.dimensions[0].findings, ["REQUIRED_PLACEHOLDER"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
