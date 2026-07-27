import { expect, test } from "@playwright/test";

import { seedScenario } from "./helpers";

test("unsupported eligibility remains visible and server-gated from export", async ({
  page,
  request,
}) => {
  await seedScenario(request, "unsupported_eligibility");
  await page.goto("/studies/synthetic-phase-2/draft");

  await expect(
    page.getByRole("region", { name: "eligibility" }).getByText("unsupported eligibility criterion"),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Create export" })).toBeDisabled();
});
