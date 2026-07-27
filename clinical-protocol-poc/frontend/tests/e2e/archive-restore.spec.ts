import { expect, test } from "@playwright/test";

import { createStudy, uploadSupportedInputs } from "./helpers";

test("archiving makes the workspace read-only and restore returns it to active work", async ({ page }) => {
  const name = "Archive and restore journey";
  const studyHref = await createStudy(page, name);
  await page.goto(studyHref);
  await uploadSupportedInputs(page);

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

  await page.goto(studyHref);
  await expect(page.getByRole("button", { name: "Process synopsis" })).toBeEnabled();
});
