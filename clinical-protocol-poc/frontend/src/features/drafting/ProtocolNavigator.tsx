import React from "react";

import type { DraftPassage } from "../../lib/types";

export function ProtocolNavigator({ passages }: Readonly<{ passages: DraftPassage[] }>) {
  return (
    <nav aria-label="Protocol sections">
      <h2>Protocol sections</h2>
      <ol>
        {passages.map((passage) => (
          <li key={passage.id}>
            <a href={`#${passage.id}-heading`}>{passage.section}</a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
