import React from "react";

export function ImpactPanel({ impact }: Readonly<{ impact: string[] }>) {
  return (
    <aside aria-label="Passage downstream impact">
      <h2>Impact</h2>
      <ul>
        {impact.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </aside>
  );
}
