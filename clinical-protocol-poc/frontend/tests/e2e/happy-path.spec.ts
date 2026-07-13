import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";

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

  const links = page.getByRole("link", { name: /^Download / });
  await expect(links).toHaveCount(3);
  await expect(page.getByTestId("artifact-snapshot-ids")).toContainText(snapshot ?? "");

  const expectedNames = ["protocol.docx", "traceability.csv", "scorecard.html"];
  for (let index = 0; index < expectedNames.length; index += 1) {
    const link = links.nth(index);
    await expect(link).toHaveText(`Download ${expectedNames[index]}`);
    const href = await link.getAttribute("href");
    expect(href).toBeTruthy();
    const response = await request.get(href!);
    expect(response.ok()).toBeTruthy();
    const body = await response.body();
    const row = await link.locator("xpath=..").textContent();
    const displayedHash = row?.match(/[a-f0-9]{64}/)?.[0];
    expect(createHash("sha256").update(body).digest("hex")).toBe(displayedHash);
    if (expectedNames[index] === "protocol.docx") {
      expect(body.subarray(0, 2).toString()).toBe("PK");
    } else if (expectedNames[index] === "traceability.csv") {
      expect(body.toString()).toContain("section,passage,claim,fact_value,evidence_location");
      expect(body.toString()).toContain('""paragraph"":4');
    } else {
      const html = body.toString();
      expect(html).toContain("Synthetic POC output only");
      expect(html).not.toContain("readiness percentage");
    }
  }
});
