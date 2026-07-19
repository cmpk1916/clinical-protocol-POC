import React from "react";

import type { ReviewItem } from "../../lib/types";

export function EvidenceComparison({ item }: Readonly<{ item: ReviewItem }>) {
  return (
    <dl aria-label={`Evidence comparison for ${item.label}`}>
      <div>
        <dt>Current approved value</dt>
        <dd>{item.currentValue}</dd>
      </div>
      <div>
        <dt>Candidate value</dt>
        <dd>{item.candidateValue}</dd>
      </div>
      <div>
        <dt>Exact evidence location</dt>
        <dd>{item.evidenceLocation}</dd>
      </div>
      <div>
        <dt>Exact source evidence</dt>
        <dd><blockquote>{item.evidenceText}</blockquote></dd>
      </div>
      <div>
        <dt>Confidence</dt>
        <dd>{Math.round(item.confidence * 100)}% confidence, supporting metadata only</dd>
      </div>
    </dl>
  );
}
