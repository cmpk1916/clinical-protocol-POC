"use client";

import React, { FormEvent, useState } from "react";

import type { StudySummary } from "../../lib/types";

type StudyPayload = {
  id: string;
  name: string;
  version: number;
  lifecycle: "active" | "archived";
  updated_at: string;
  archived_at: string | null;
};

function toSummary(study: StudyPayload): StudySummary {
  return {
    id: study.id,
    name: study.name,
    version: study.version,
    lifecycle: study.lifecycle,
    updatedAt: study.updated_at,
    archivedAt: study.archived_at,
  };
}

async function loadStudies(lifecycle: "active" | "archived"): Promise<StudySummary[]> {
  const response = await fetch(`/api/local/studies?lifecycle=${lifecycle}`);
  if (!response.ok) {
    throw new Error(`Unable to load ${lifecycle} studies`);
  }
  const payload = (await response.json()) as { items: StudyPayload[] };
  return payload.items.map(toSummary);
}

export function StudyDashboard({
  initialActive,
  initialArchived,
}: {
  initialActive: StudySummary[];
  initialArchived: StudySummary[];
}) {
  const [active, setActive] = useState(initialActive);
  const [archived, setArchived] = useState(initialArchived);
  const [view, setView] = useState<"active" | "archived">("active");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [nextActive, nextArchived] = await Promise.all([
      loadStudies("active"),
      loadStudies("archived"),
    ]);
    setActive(nextActive);
    setArchived(nextArchived);
  }

  async function createStudy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/local/studies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!response.ok) throw new Error("Unable to create study");
      setName("");
      setView("active");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create study");
    } finally {
      setBusy(false);
    }
  }

  async function changeLifecycle(study: StudySummary, command: "archive" | "restore") {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/local/studies/${encodeURIComponent(study.id)}/${command}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_version: study.version }),
      });
      if (!response.ok) throw new Error(`Unable to ${command} study`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Unable to ${command} study`);
    } finally {
      setBusy(false);
    }
  }

  const studies = view === "active" ? active : archived;

  return (
    <main className="dashboard-shell">
      <header className="hero">
        <p className="eyebrow">Clinical Protocol POC</p>
        <h1>Study workspace</h1>
        <p>Build and review protocol drafts using synthetic data only.</p>
      </header>

      <section className="create-panel" aria-labelledby="create-heading">
        <div>
          <h2 id="create-heading">Start a synthetic study</h2>
          <p>Create a workspace before adding facts, evidence, and draft passages.</p>
        </div>
        <form onSubmit={createStudy}>
          <label htmlFor="study-name">Study name</label>
          <div className="create-row">
            <input
              id="study-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Synthetic Alpha"
              disabled={busy}
            />
            <button type="submit" disabled={busy || !name.trim()}>Create study</button>
          </div>
        </form>
      </section>

      {error ? <p role="alert" className="error-banner">{error}</p> : null}

      <section className="study-panel" aria-labelledby="studies-heading">
        <div className="study-heading">
          <h2 id="studies-heading">Studies</h2>
          <div role="tablist" aria-label="Study lifecycle">
            <button role="tab" aria-selected={view === "active"} onClick={() => setView("active")}>Active</button>
            <button role="tab" aria-selected={view === "archived"} onClick={() => setView("archived")}>Archived</button>
          </div>
        </div>

        {studies.length === 0 ? (
          <div className="empty-state">
            <h3>No {view} studies</h3>
            <p>This local proof of concept accepts synthetic data only. Do not use real patient or confidential protocol data.</p>
          </div>
        ) : (
          <div className="study-grid">
            {studies.map((study) => (
              <article key={study.id} className="study-card">
                <div>
                  <p className="status">{study.lifecycle}</p>
                  <h3>{study.name}</h3>
                  <p>Updated {new Date(study.updatedAt).toLocaleDateString()}</p>
                </div>
                <div className="card-actions">
                  {study.lifecycle === "active" ? (
                    <>
                      <a href={`/studies/${encodeURIComponent(study.id)}`} aria-label={`Open ${study.name}`}>Open study</a>
                      <button disabled={busy} onClick={() => changeLifecycle(study, "archive")} aria-label={`Archive ${study.name}`}>Archive</button>
                    </>
                  ) : (
                    <button disabled={busy} onClick={() => changeLifecycle(study, "restore")} aria-label={`Restore ${study.name}`}>Restore</button>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
