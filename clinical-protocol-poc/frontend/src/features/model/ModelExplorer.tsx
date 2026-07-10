"use client";

import React from "react";
import { KeyboardEvent, useEffect, useRef, useState } from "react";

import type { StudyModel } from "../../lib/types";

export function ModelExplorer({ model }: Readonly<{ model: StudyModel }>) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const treeRef = useRef<HTMLUListElement>(null);
  const selectedFact = model.facts[selectedIndex];

  useEffect(() => {
    treeRef.current?.focus();
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedIndex((current) => Math.min(current + 1, model.facts.length - 1));
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedIndex((current) => Math.max(current - 1, 0));
    }
  };

  return (
    <section aria-labelledby="model-explorer-heading">
      <h1 id="model-explorer-heading">Model Explorer</h1>
      <ul
        ref={treeRef}
        role="tree"
        aria-label="Canonical study facts"
        tabIndex={0}
        onKeyDown={onKeyDown}
        style={{ color: "#111827", background: "#ffffff" }}
      >
        {model.facts.map((fact, index) => (
          <li
            aria-selected={index === selectedIndex}
            key={fact.id}
            role="treeitem"
            onClick={() => setSelectedIndex(index)}
          >
            <strong>{fact.label}</strong>: {fact.value} · {fact.status} · {fact.version}
          </li>
        ))}
      </ul>

      <section aria-label="All model conflicts">
        <h2>Conflicts</h2>
        {model.facts.some((fact) => fact.conflicts.length > 0) ? (
          <ul>
            {model.facts.flatMap((fact) =>
              fact.conflicts.map((conflict) => (
                <li key={`${fact.id}-${conflict}`}>
                  {fact.label}: <span>{conflict}</span>
                </li>
              )),
            )}
          </ul>
        ) : (
          <p>No conflicts recorded.</p>
        )}
      </section>
      <section aria-label="All fact impact and relationship alternatives">
        <h2>Impact and relationship alternatives</h2>
        <ul>
          {model.facts.map((fact) => (
            <li key={`${fact.id}-summary`}>
              <p>Affected passages: {fact.affectedPassages.join(", ")}</p>
              {fact.relationships.map((relationship) => (
                <p key={`${fact.id}-${relationship.label}-${relationship.target}`}>
                  Text alternative: {fact.label} {relationship.label} {relationship.target}
                </p>
              ))}
            </li>
          ))}
        </ul>
      </section>

      {selectedFact ? (
        <article aria-labelledby="selected-fact-heading">
          <h2 id="selected-fact-heading" data-testid="selected-fact">
            {selectedFact.label}
          </h2>
          <p>Status: {selectedFact.status}</p>
          <p>Version: {selectedFact.version}</p>
          <p>Provenance: {selectedFact.provenance.join(", ")}</p>
          {selectedFact.conflicts.length ? (
            <section aria-label="Conflicts">
              <h3>Conflicts</h3>
              <ul>
                {selectedFact.conflicts.map((conflict) => (
                  <li key={conflict}>{conflict}</li>
                ))}
              </ul>
            </section>
          ) : (
            <p>No conflicts recorded.</p>
          )}
          <p>Affected passages: {selectedFact.affectedPassages.join(", ")}</p>
          <section aria-label="Relationships">
            <h3>Relationships</h3>
            <ul>
              {selectedFact.relationships.map((relationship) => (
                <li key={`${relationship.label}-${relationship.target}`}>
                  {selectedFact.label} {relationship.label} {relationship.target}
                </li>
              ))}
            </ul>
            <p>
              Text alternative:{" "}
              {selectedFact.relationships
                .map(
                  (relationship) =>
                    `${selectedFact.label} ${relationship.label} ${relationship.target}`,
                )
                .join("; ")}
            </p>
          </section>
        </article>
      ) : null}
    </section>
  );
}
