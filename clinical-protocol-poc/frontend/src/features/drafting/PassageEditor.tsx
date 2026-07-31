"use client";

import React, { useState } from "react";

import type { DraftPassage, PassageApi, PassageFinding } from "../../lib/types";
import { EvidencePanel } from "./EvidencePanel";
import { ImpactPanel } from "./ImpactPanel";

export function PassageEditor({
  passage,
  api,
  readOnly = false,
  onUpdated,
}: Readonly<{
  passage: DraftPassage;
  api: PassageApi;
  readOnly?: boolean;
  onUpdated?: (passage: DraftPassage) => void | Promise<void>;
}>) {
  const [text, setText] = useState(passage.text);
  const [findings, setFindings] = useState<PassageFinding[]>(passage.findings);
  const [currentVersion, setCurrentVersion] = useState(passage.version);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const blocked = readOnly || passage.stale || findings.length > 0 || passage.status === "draft" || passage.status === "blocked" || passage.status === "rejected" || passage.status === "accepted";
  const supportIds = passage.evidence
    .map((item) => item.replace("Approved fact support: ", ""))
    .filter((item) => item !== "");

  async function command(action: "accept" | "edit" | "reject" | "regenerate") {
    if (!api.reviewPassage || currentVersion === undefined) {
      setError("Passage review is unavailable until the saved passage is refreshed.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.reviewPassage({
        passageId: passage.id,
        action,
        expectedVersion: currentVersion,
        ...(action === "edit" ? { text, supportIds } : {}),
        ...(action === "reject" ? { rationale: "Synthetic writer rejection." } : {}),
      });
      setText(updated.text);
      setFindings(updated.findings);
      setCurrentVersion(updated.version);
      await onUpdated?.(updated);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save passage review");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={`${passage.id}-heading`}>
      <h1 id={`${passage.id}-heading`}>{passage.section}</h1>
      {readOnly ? <p role="status">This archived passage review is read-only. Saved passage evidence remains available.</p> : null}
      {passage.stale ? <p role="alert">Stale passage: revalidate before accepting.</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {busy ? <p role="status">Saving passage review…</p> : null}
      <label htmlFor={`${passage.id}-text`}>Passage text</label>
      <textarea
        id={`${passage.id}-text`}
        value={text}
        disabled={readOnly || busy}
        onChange={(event) => setText(event.currentTarget.value)}
      />
      <section aria-label="Validation findings">
        <h2>Findings</h2>
        {findings.length ? (
          <ul>
            {findings.map((finding) => (
              <li key={`${finding.code}-${finding.message}`}>
                {finding.message} <span className="finding-code">({finding.code})</span>
              </li>
            ))}
          </ul>
        ) : (
          <p>No validation findings.</p>
        )}
      </section>
      <EvidencePanel evidence={passage.evidence} guidance={passage.guidance} />
      <ImpactPanel impact={passage.impact} />
      <menu aria-label="Passage actions">
        <button
          type="button"
          disabled={readOnly || busy}
          onClick={() => void command("edit")}
        >
          Validate passage
        </button>
        <button type="button" disabled={blocked || busy} onClick={() => void command("accept")}>Accept passage</button>
        <button type="button" disabled={readOnly || busy} onClick={() => void command("edit")}>Edit passage</button>
        <button type="button" disabled={readOnly || busy} onClick={() => void command("reject")}>Reject passage</button>
        <button type="button" disabled={readOnly || busy} onClick={() => void command("regenerate")}>Regenerate passage</button>
      </menu>
    </section>
  );
}
