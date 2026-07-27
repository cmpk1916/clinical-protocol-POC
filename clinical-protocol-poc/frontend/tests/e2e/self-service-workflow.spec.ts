import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { inflateRawSync } from "node:zlib";

import {
  createStudy,
  generateAndAcceptPassages,
  processSynopsis,
  reviewAllFacts,
  uploadSupportedInputs,
} from "./helpers";

function zipEntry(body: Buffer, name: string): string {
  let offset = 0;
  while (body.readUInt32LE(offset) === 0x04034b50) {
    const compression = body.readUInt16LE(offset + 8);
    const compressedSize = body.readUInt32LE(offset + 18);
    const filenameLength = body.readUInt16LE(offset + 26);
    const extraLength = body.readUInt16LE(offset + 28);
    const filename = body.subarray(offset + 30, offset + 30 + filenameLength).toString();
    const contentStart = offset + 30 + filenameLength + extraLength;
    const content = body.subarray(contentStart, contentStart + compressedSize);
    if (filename === name) {
      return (compression === 8 ? inflateRawSync(content) : content).toString();
    }
    offset = contentStart + compressedSize;
  }
  throw new Error(`ZIP entry not found: ${name}`);
}

test("empty workspace reaches a governed three-artifact export", async ({ page, request }) => {
  // This journey executes the full server-backed review and export path; allow
  // each explicit review refresh to settle under the release Docker stack.
  test.setTimeout(180_000);
  const studyHref = await createStudy(page, "Self-service export journey");
  await page.goto(studyHref);
  await expect(page.getByText("Upload a supported synopsis DOCX to continue.")).toBeVisible();

  await uploadSupportedInputs(page);
  await processSynopsis(page);
  await page.goto(`${studyHref}/review`);
  await reviewAllFacts(page);
  await generateAndAcceptPassages(page, studyHref);

  await page.getByRole("button", { name: "Create export" }).click();
  const snapshot = await page.getByTestId("snapshot-id").textContent();
  expect(snapshot).toBeTruthy();
  const links = page.getByRole("link", { name: /^Download / });
  await expect(links).toHaveCount(3);
  await expect(page.getByTestId("artifact-snapshot-ids")).toContainText(snapshot!);
  const artifactDirectory = resolve(process.cwd(), "test-results/self-service-artifacts");
  await mkdir(artifactDirectory, { recursive: true });

  for (const name of ["protocol.docx", "traceability.csv", "scorecard.html"]) {
    const link = page.getByRole("link", { name: `Download ${name}` });
    const href = await link.getAttribute("href");
    expect(href).toBeTruthy();
    const response = await request.get(href!);
    expect(response.ok()).toBeTruthy();
    const body = await response.body();
    const row = await link.locator("xpath=..").textContent();
    expect(createHash("sha256").update(body).digest("hex")).toBe(row?.match(/[a-f0-9]{64}/)?.[0]);
    expect(row).toContain(snapshot!);
    await writeFile(resolve(artifactDirectory, name), body);

    if (name === "protocol.docx") {
      expect(body.subarray(0, 2).toString()).toBe("PK");
      expect(zipEntry(body, "word/document.xml")).not.toContain("[[");
    } else if (name === "traceability.csv") {
      const text = body.toString();
      expect(text).not.toContain("[[");
      const rows = text.trim().split("\n");
      expect(rows[0]).toBe(
        "section,passage,claim,fact_value,evidence_location,guidance_release,review_state,validation_status",
      );
      expect(rows.slice(1)).not.toHaveLength(0);
      for (const traceabilityRow of rows.slice(1)) {
        expect(traceabilityRow).toMatch(/""part"":""word\/document.xml""/);
        expect(traceabilityRow).toMatch(/""index"":\d+/);
      }
    } else {
      const text = body.toString();
      expect(text).not.toContain("[[");
      expect(text).toContain(
        "Synthetic POC output only; not validated and no clinical, regulatory, submission, operational, or readiness claim is made.",
      );
      expect(text).not.toContain("readiness percentage");
    }
  }
});

test("reopening a study resumes its persisted next safe action", async ({ page }) => {
  const studyHref = await createStudy(page, "Self-service resume journey");
  await page.goto(studyHref);
  await uploadSupportedInputs(page);
  await page.reload();

  await expect(page.getByRole("article", { name: "Synopsis" })).toContainText("Version 1");
  await expect(page.getByRole("article", { name: "Protocol template" })).toContainText("Version 1");
  await expect(page.getByRole("button", { name: "Process synopsis" })).toBeVisible();
});
