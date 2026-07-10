"use client";

import React from "react";
import { useState } from "react";

import { demoPassageApi } from "../../lib/api";
import type { DraftPassage, PassageApi, PassageFinding } from "../../lib/types";
import { EvidencePanel } from "./EvidencePanel";
import { ImpactPanel } from "./ImpactPanel";

export function PassageEditor({
  passage,
  api = demoPassageApi,
}: Readonly<{ passage: DraftPassage; api?: PassageApi }>) {
  const [text, setText] = useState(passage.text);
  const [findings, setFindings] = useState<PassageFinding[]>(passage.findings);
  const blocked = passage.stale || findings.length > 0 || passage.status === "blocked";

  return (
    <section aria-labelledby={`${passage.id}-heading`}>
      <h1 id={`${passage.id}-heading`}>{passage.section}</h1>
      {passage.stale ? <p role="alert">Stale passage: revalidate before accepting.</p> : null}
      <label htmlFor={`${passage.id}-text`}>Passage text</label>
      <textarea
        id={`${passage.id}-text`}
        value={text}
        onChange={(event) => setText(event.currentTarget.value)}
      />
      <section aria-label="Validation findings">
        <h2>Findings</h2>
        {findings.length ? (
          <ul>
            {findings.map((finding) => (
              <li key={`${finding.code}-${finding.message}`}>{finding.message}</li>
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
          onClick={async () => {
            const result = await api.validatePassage({ passageId: passage.id, text });
            setFindings(result.findings);
          }}
        >
          Validate passage
        </button>
        <button
          type="button"
          disabled={blocked}
          onClick={() => void api.acceptPassage({ passageId: passage.id, text })}
        >
          Accept passage
        </button>
        <button type="button">Edit passage</button>
        <button type="button">Reject passage</button>
        <button type="button">Regenerate passage</button>
      </menu>
    </section>
  );
}
