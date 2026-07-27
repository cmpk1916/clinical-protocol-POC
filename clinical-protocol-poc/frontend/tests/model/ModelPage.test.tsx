import assert from "node:assert/strict";
import { describe, it } from "node:test";

import ModelPage from "../../src/app/studies/[studyId]/model/page";

describe("ModelPage", () => {
  it("redirects to the authoritative fact review route", async () => {
    await assert.rejects(
      () => ModelPage({ params: Promise.resolve({ studyId: "study-1" }) }),
      (error: unknown) => {
        assert.match(String((error as { digest?: string }).digest), /\/studies\/study-1\/review/);
        return true;
      },
    );
  });
});
