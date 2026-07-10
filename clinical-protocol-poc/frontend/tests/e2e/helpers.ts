import { expect, type APIRequestContext, type Page } from "@playwright/test";

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
