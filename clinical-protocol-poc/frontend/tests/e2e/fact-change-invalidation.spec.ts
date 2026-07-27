import { expect, test } from "@playwright/test";

import { seedScenario } from "./helpers";

test("changing an approved dose marks its passage stale and denies export", async ({
  page,
  request,
}) => {
  await seedScenario(request, "fact_change_invalidation");
  await page.goto("/studies/synthetic-phase-2/draft");

  await expect(page.getByText("Stale passage: revalidate before accepting.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Export" }).getByText("STALE_PASSAGE")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "study design" }).getByRole("button", { name: "Accept passage" }),
  ).toBeDisabled();
  await expect(page.getByRole("button", { name: "Create export" })).toBeDisabled();
});
