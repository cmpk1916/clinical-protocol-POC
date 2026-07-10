import { expect, test } from "@playwright/test";

import { acceptAllValidPassages, reviewAllRequiredFacts, seedScenario } from "./helpers";

test("writer reviews facts, accepts passages, and exports one snapshot", async ({
  page,
  request,
}) => {
  await seedScenario(request, "happy_path");
  await page.goto("/studies/synthetic-phase-2/review");
  await reviewAllRequiredFacts(page);
  await page.goto("/studies/synthetic-phase-2/draft");
  await acceptAllValidPassages(page);
  await page.getByRole("button", { name: "Create export" }).click();
  const snapshot = await page.getByTestId("snapshot-id").textContent();

  await expect(page.getByText("protocol.docx")).toBeVisible();
  await expect(page.getByText("traceability.csv")).toBeVisible();
  await expect(page.getByText("scorecard.html")).toBeVisible();
  await expect(page.getByTestId("artifact-snapshot-ids")).toContainText(snapshot ?? "");
});
