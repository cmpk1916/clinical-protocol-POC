import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const fixtureDirectory = resolve(process.cwd(), "../fixtures/self-service");

export function supportedFixture(name: "synopsis.docx" | "template.docx"): string {
  return resolve(fixtureDirectory, name);
}

export async function replacementFixture(
  source: "synopsis.docx" | "template.docx",
  name: string,
): Promise<{ name: string; mimeType: string; buffer: Buffer }> {
  const original = await readFile(supportedFixture(source));
  const endOfCentralDirectory = original.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (endOfCentralDirectory < 0) throw new Error("DOCX end-of-central-directory record is missing");
  const comment = Buffer.from(`replacement:${name}`, "utf8");
  const buffer = Buffer.concat([original, comment]);
  buffer.writeUInt16LE(comment.length, endOfCentralDirectory + 20);
  return {
    name,
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer,
  };
}

export async function createStudy(page: Page, name: string): Promise<string> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Study workspace" })).toBeVisible();
  await page.getByLabel("Study name").fill(name);
  await page.getByRole("button", { name: "Create study" }).click();
  const study = page.getByRole("link", { name: `Open ${name}` });
  await expect(study).toBeVisible();
  const href = await study.getAttribute("href");
  expect(href).toMatch(/^\/studies\/[^/]+$/);
  return href!;
}

export async function uploadSupportedInputs(page: Page): Promise<void> {
  await page.getByLabel("Synopsis DOCX").setInputFiles(supportedFixture("synopsis.docx"));
  await page.getByRole("button", { name: "Upload synopsis" }).click();
  await expect(page.getByRole("article", { name: "Synopsis" })).toContainText("synopsis.docx");

  await page.getByLabel("Template DOCX").setInputFiles(supportedFixture("template.docx"));
  await page.getByRole("button", { name: "Upload template" }).click();
  await expect(page.getByRole("article", { name: "Protocol template" })).toContainText("template.docx");
  await expect(page.getByRole("button", { name: "Process synopsis" })).toBeVisible();
}

export async function processSynopsis(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Process synopsis" }).click();
  await expect(page.getByRole("link", { name: /Review \d+ candidate facts/ })).toBeVisible();
}

export async function reviewAllFacts(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { name: "Guided Review" })).toBeVisible();

  const enabledApprovalButtons = page.locator("button:enabled").filter({ hasText: "Approve fact" });
  const approvals = await enabledApprovalButtons.count();
  expect(approvals).toBeGreaterThan(0);
  for (let remaining = approvals; remaining > 0; remaining -= 1) {
    await expect(enabledApprovalButtons).toHaveCount(remaining);
    await enabledApprovalButtons.first().click();
    const confirmation = page.getByLabel("I explicitly confirm this critical fact");
    if (await confirmation.count()) {
      await confirmation.check();
      await page.getByRole("button", { name: "Confirm approval" }).click();
    }
    await expect.poll(async () => enabledApprovalButtons.count()).toBe(remaining - 1);
  }
  await expect(page.getByRole("status")).toContainText("All candidate facts have been reviewed.");
}

export async function generateAndAcceptPassages(page: Page, studyHref: string): Promise<void> {
  await page.goto(`${studyHref}/draft`);
  const generationButtons = page.getByRole("button", { name: /^Generate / });
  await expect(generationButtons).toHaveCount(4);
  for (let remaining = 4; remaining > 0; remaining -= 1) {
    await expect(generationButtons).toHaveCount(remaining);
    const button = generationButtons.first();
    await button.click();
    await expect(generationButtons).toHaveCount(remaining - 1);
  }
  await expect(page.getByRole("button", { name: "Accept passage" })).toHaveCount(4);
  const enabledAcceptanceButtons = page.locator("button:enabled").filter({ hasText: "Accept passage" });
  const navigator = page.getByRole("navigation", { name: "Protocol sections" });
  for (let remaining = 4; remaining > 0; remaining -= 1) {
    await expect(enabledAcceptanceButtons).toHaveCount(remaining);
    const button = enabledAcceptanceButtons.first();
    await button.click();
    await expect(navigator).toContainText(`${5 - remaining} of 4 sections saved`);
  }
  await expect(page.getByRole("button", { name: "Create export" })).toBeEnabled();
}

export async function seedScenario(
  request: APIRequestContext,
  scenario: string,
): Promise<void> {
  const apiUrl = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
  await request.post(`${apiUrl}/test/reset`);
  const response = await request.post(
    `${apiUrl}/test/studies/synthetic-phase-2/seed`,
    { data: { scenario } },
  );
  expect(response.ok()).toBeTruthy();
}

export async function reviewAllRequiredFacts(page: Page): Promise<void> {
  await expect(page.getByText("Dose requires review before export.")).toBeVisible();
  await page.getByRole("button", { name: "Approve fact" }).click();
  await page.getByLabel("I explicitly confirm this critical fact").check();
  await page.getByRole("button", { name: "Confirm approval" }).click();
  await expect(page.getByRole("status")).toContainText("All candidate facts have been reviewed.");
}

export async function acceptAllValidPassages(page: Page): Promise<void> {
  const button = page.locator("button:enabled").filter({ hasText: "Accept passage" });
  await expect(button).toHaveCount(1);
  await expect(button).toBeEnabled();
  await button.click();
}
