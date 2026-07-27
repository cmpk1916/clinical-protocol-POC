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

export async function processAndReviewFacts(page: Page, studyHref: string): Promise<void> {
  await page.getByRole("button", { name: "Process synopsis" }).click();
  await expect(page.getByRole("link", { name: /Review \d+ candidate facts/ })).toBeVisible();
  await page.goto(`${studyHref}/review`);
  await expect(page.getByRole("heading", { name: "Guided Review" })).toBeVisible();

  while (await page.getByRole("button", { name: "Approve fact" }).count()) {
    await page.getByRole("button", { name: "Approve fact" }).first().click();
    const confirmation = page.getByLabel("I explicitly confirm this critical fact");
    if (await confirmation.count()) {
      await confirmation.check();
      await page.getByRole("button", { name: "Confirm approval" }).click();
    }
    await expect(
      page.getByRole("button", { name: "Approve fact" }).or(page.getByRole("status")).first(),
    ).toBeVisible();
  }
  await expect(page.getByRole("status")).toContainText("All candidate facts have been reviewed.");
}

export async function generateAndAcceptPassages(page: Page, studyHref: string): Promise<void> {
  await page.goto(`${studyHref}/draft`);
  while (await page.getByRole("button", { name: /^Generate / }).count()) {
    const button = page.getByRole("button", { name: /^Generate / }).first();
    const label = await button.textContent();
    expect(label).toBeTruthy();
    await button.click();
    await expect(page.getByRole("button", { name: label! })).toHaveCount(0);
  }
  await expect(page.getByRole("button", { name: "Accept passage" })).toHaveCount(4);
  while (await page.locator("button:enabled").filter({ hasText: "Accept passage" }).count()) {
    const button = page.locator("button:enabled").filter({ hasText: "Accept passage" }).first();
    const count = await page.locator("button:enabled").filter({ hasText: "Accept passage" }).count();
    await button.click();
    await expect.poll(async () => page.locator("button:enabled").filter({ hasText: "Accept passage" }).count()).toBe(count - 1);
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
  await expect(page.getByText(/Export blocked: 1 critical fact/)).toBeVisible();
  await page.getByRole("button", { name: "Approve fact" }).click();
  await page.getByLabel("I explicitly confirm this critical fact").check();
  await page.getByRole("button", { name: "Confirm approval" }).click();
}

export async function acceptAllValidPassages(page: Page): Promise<void> {
  const button = page.getByRole("button", { name: "Accept passage" });
  await expect(button).toBeEnabled();
  await button.click();
}
