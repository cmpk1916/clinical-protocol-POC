import { expect, test } from "@playwright/test";

import {
  createStudy,
  generateAndAcceptPassages,
  processAndReviewFacts,
  replacementFixture,
  uploadSupportedInputs,
} from "./helpers";

test("synopsis replacement supersedes the current input and requires re-review", async ({ page }) => {
  test.setTimeout(90_000);
  const studyHref = await createStudy(page, "Synopsis replacement journey");
  await page.goto(studyHref);
  await uploadSupportedInputs(page);
  await processAndReviewFacts(page, studyHref);
  await generateAndAcceptPassages(page, studyHref);
  await page.goto(studyHref);

  await page.getByLabel("Synopsis DOCX").setInputFiles(
    await replacementFixture("synopsis.docx", "synopsis-replacement.docx"),
  );
  await page.getByRole("button", { name: "Upload synopsis" }).click();
  await expect(page.getByRole("heading", { name: "Confirm replacement" })).toBeVisible();
  await expect(page.getByText("invalidate dependent passages")).toBeVisible();
  await page.getByRole("button", { name: "Confirm replacement" }).click();
  await expect(page.getByRole("article", { name: "Synopsis" })).toContainText("synopsis-replacement.docx");
  await expect(page.getByRole("article", { name: "Synopsis" })).toContainText("Version 2");
  await expect(page.getByRole("link", { name: /Review \d+ candidate facts/ })).toBeVisible();

  await page.goto(`${studyHref}/review`);
  await expect(page.getByRole("button", { name: "Approve fact" })).toBeVisible();
  await processAndReviewFacts(page, studyHref);
});

test("template replacement keeps accepted passages and enables a revalidated export", async ({ page }) => {
  test.setTimeout(90_000);
  const studyHref = await createStudy(page, "Template replacement journey");
  await page.goto(studyHref);
  await uploadSupportedInputs(page);
  await processAndReviewFacts(page, studyHref);
  await generateAndAcceptPassages(page, studyHref);
  await page.goto(studyHref);

  await page.getByLabel("Template DOCX").setInputFiles(
    await replacementFixture("template.docx", "template-replacement.docx"),
  );
  await page.getByRole("button", { name: "Upload template" }).click();
  await expect(page.getByRole("heading", { name: "Confirm replacement" })).toBeVisible();
  await expect(page.getByText("preserve facts and passage reviews")).toBeVisible();
  await page.getByRole("button", { name: "Confirm replacement" }).click();
  await expect(page.getByRole("article", { name: "Protocol template" })).toContainText("template-replacement.docx");
  await expect(page.getByRole("article", { name: "Protocol template" })).toContainText("Version 2");

  await page.goto(`${studyHref}/draft`);
  await expect(page.getByRole("button", { name: "Accept passage" })).toHaveCount(4);
  await expect(page.getByRole("button", { name: "Create export" })).toBeEnabled();
});

test("an invalid DOCX upload leaves the current synopsis visible and unchanged", async ({ page }) => {
  const studyHref = await createStudy(page, "Invalid replacement journey");
  await page.goto(studyHref);
  await uploadSupportedInputs(page);

  await page.getByLabel("Synopsis DOCX").setInputFiles({
    name: "not-a-docx.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("not a ZIP package"),
  });
  await page.getByRole("button", { name: "Upload synopsis" }).click();
  await expect(page.getByRole("alert")).toContainText(/Unable to upload synopsis|invalid/i);
  await expect(page.getByRole("article", { name: "Synopsis" })).toContainText("synopsis.docx");
  await expect(page.getByRole("article", { name: "Synopsis" })).toContainText("Version 1");
  await expect(page.getByRole("button", { name: "Process synopsis" })).toBeVisible();
});
