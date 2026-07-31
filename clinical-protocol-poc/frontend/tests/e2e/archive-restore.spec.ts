import { expect, test } from "@playwright/test";

import {
  createStudy,
  generateAndAcceptPassages,
  processSynopsis,
  reviewAllFacts,
  uploadSupportedInputs,
} from "./helpers";

test("archiving makes the workspace read-only and restore returns it to active work", async ({ page }) => {
  test.setTimeout(180_000);
  const name = "Archive and restore journey";
  const studyHref = await createStudy(page, name);
  await page.goto(studyHref);
  await uploadSupportedInputs(page);
  await processSynopsis(page);
  await page.goto(`${studyHref}/review`);
  await reviewAllFacts(page);
  await generateAndAcceptPassages(page, studyHref);
  await page.getByRole("button", { name: "Create export" }).click();
  const snapshot = await page.getByTestId("snapshot-id").textContent();
  expect(snapshot).toBeTruthy();
  await expect(page.getByRole("link", { name: /^Download / })).toHaveCount(3);

  await page.goto("/");
  await page.getByRole("button", { name: `Archive ${name}` }).click();
  await expect(page.getByText("No active studies")).toBeVisible();
  await page.getByRole("tab", { name: "Archived" }).click();
  await expect(page.getByText(name)).toBeVisible();

  await page.goto(studyHref);
  await expect(page.getByRole("status")).toContainText("archived workspace is read-only");
  await expect(page.getByLabel("Synopsis DOCX")).toBeDisabled();
  await expect(page.getByRole("link", { name: "Restore from the study dashboard" })).toBeVisible();

  await page.goto("/");
  await page.getByRole("tab", { name: "Archived" }).click();
  await page.getByRole("button", { name: `Restore ${name}` }).click();
  await expect(page.getByRole("heading", { name })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Active" })).toBeVisible();
  await page.getByRole("tab", { name: "Active" }).click();
  await expect(page.getByRole("link", { name: `Open ${name}` })).toBeVisible();

  await page.goto(`${studyHref}/draft`);
  await expect(page.getByTestId("snapshot-id")).toHaveText(snapshot!);
  await expect(page.getByRole("link", { name: /^Download / })).toHaveCount(3);
  await expect(page.getByRole("link", { name: "Download protocol.docx" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download traceability.csv" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download scorecard.html" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create export" })).toHaveCount(0);
});
