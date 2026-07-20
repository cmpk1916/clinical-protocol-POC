import React from "react";

import type { DraftPassage } from "../../lib/types";

const governedSections = ["synopsis", "objectives_endpoints", "study_design", "eligibility"] as const;

export function ProtocolNavigator({ passages }: Readonly<{ passages: DraftPassage[] }>) {
  const savedSections = passages.filter((passage) => passage.status === "accepted").length;
  return (
    <nav aria-label="Protocol sections">
      <h2>Protocol sections</h2>
      <p>{savedSections} of {governedSections.length} sections saved</p>
      <ol>
        {governedSections.map((section) => {
          const passage = passages.find((item) => item.section === section.replaceAll("_", " "));
          const label = section.replaceAll("_", " ");
          return (
            <li key={section}>
              {passage ? <a href={`#${passage.id}-heading`}>{passage.section}</a> : <span>{label} — missing</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
