import React from "react";

export function EvidencePanel({
  evidence,
  guidance,
}: Readonly<{ evidence: string[]; guidance: string[] }>) {
  return (
    <aside aria-label="Evidence and guidance support">
      <h2>Evidence and guidance</h2>
      <h3>Evidence</h3>
      <ul>
        {evidence.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <h3>Guidance</h3>
      <ul>
        {guidance.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </aside>
  );
}
