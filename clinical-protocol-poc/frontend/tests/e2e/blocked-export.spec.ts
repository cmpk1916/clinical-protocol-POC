import { expect, test } from "@playwright/test";

import {
  createStudy,
  generatePassages,
  processSynopsis,
  reviewAllFacts,
  seedScenario,
  uploadSupportedInputs,
} from "./helpers";

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

test("unsupported passage edit is blocked until explicit regeneration", async ({ page }) => {
  test.setTimeout(180_000);
  const studyHref = await createStudy(page, "Unsupported passage recovery journey");
  await page.goto(studyHref);
  await uploadSupportedInputs(page);
  await processSynopsis(page);
  await page.goto(`${studyHref}/review`);
  await reviewAllFacts(page);
  await generatePassages(page, studyHref);

  const studyDesign = page.getByRole("region", { name: "study design" });
  const passageText = studyDesign.getByLabel("Passage text");
  await passageText.fill((await passageText.inputValue()).replace("10 mg", "99 mg"));
  await studyDesign.getByRole("button", { name: "Validate passage" }).click();

  await expect(studyDesign.getByText("Dose 99 mg is not an approved fact")).toBeVisible();
  await expect(studyDesign.getByText("(UNSUPPORTED_DOSE)")).toBeVisible();
  await expect(studyDesign.getByRole("button", { name: "Accept passage" })).toBeDisabled();

  const enabledAcceptanceButtons = page.locator("button:enabled").filter({
    hasText: "Accept passage",
  });
  for (let remaining = 3; remaining > 0; remaining -= 1) {
    await expect(enabledAcceptanceButtons).toHaveCount(remaining);
    await enabledAcceptanceButtons.first().click();
  }
  await expect(page.getByRole("button", { name: "Create export" })).toBeDisabled();

  await studyDesign.getByRole("button", { name: "Regenerate passage" }).click();
  await expect(studyDesign.getByText("No validation findings.")).toBeVisible();
  await expect(studyDesign.getByRole("button", { name: "Accept passage" })).toBeEnabled();
  await studyDesign.getByRole("button", { name: "Accept passage" }).click();
  await expect(page.getByRole("button", { name: "Create export" })).toBeEnabled();
});
