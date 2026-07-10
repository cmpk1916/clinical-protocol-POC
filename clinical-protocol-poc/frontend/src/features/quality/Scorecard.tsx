import React from "react";

import type { QualityScorecard } from "../../lib/types";

export function Scorecard({ card }: Readonly<{ card: QualityScorecard }>) {
  return (
    <section aria-labelledby="scorecard-heading">
      <h2 id="scorecard-heading">Quality scorecard</h2>
      <p>{card.disclaimer}</p>
      <ul>
        {card.dimensions.map((dimension) => (
          <li key={dimension.name}>
            <h3>{dimension.name}</h3>
            <p>
              {dimension.status} · {dimension.count} finding{dimension.count === 1 ? "" : "s"}
            </p>
            {dimension.findings.length ? (
              <ul>
                {dimension.findings.map((finding) => (
                  <li key={finding}>{finding}</li>
                ))}
              </ul>
            ) : (
              <p>No findings.</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
