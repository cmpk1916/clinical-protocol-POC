"use client";

import React, { useState } from "react";

import { protocolWorkspaceApi, type WorkspaceApi } from "../../lib/api";
import type { WorkspaceSummary } from "../../lib/types";
import { InputCard } from "./InputCard";

type Props = {
  initialSummary: WorkspaceSummary;
  api?: WorkspaceApi;
};

export function WorkspaceGuide({ initialSummary, api = protocolWorkspaceApi }: Readonly<Props>) {
  const [summary, setSummary] = useState(initialSummary);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const action = summary.nextAction;

  async function runCommand() {
    setBusy(true);
    setError(null);
    try {
      let next: WorkspaceSummary;
      if (action.kind === "process_synopsis" && action.targetId) {
        next = await api.processSynopsis(summary.study.id, action.targetId);
      } else if (action.kind === "retry_processing" && action.targetId) {
        next = await api.retryProcessing(summary.study.id, action.targetId);
      } else {
        next = await api.getWorkspace(summary.study.id);
      }
      setSummary(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to update workspace");
    } finally {
      setBusy(false);
    }
  }

  const commandAction = [
    "process_synopsis",
    "retry_processing",
    "refresh_workspace",
  ].includes(action.kind);

  return (
    <main className="workspace-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Synthetic study workspace</p>
          <h1>{summary.study.name}</h1>
          <p>Saved server state determines every step and next action.</p>
        </div>
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a href="/">All studies</a>
      </header>

      {summary.readOnly ? (
        <p role="status" className="read-only-banner">
          This archived workspace is read-only. Its saved inputs, evidence, and review state remain viewable.
        </p>
      ) : null}
      {error ? <p role="alert" className="error-banner">{error}</p> : null}

      <nav aria-label="Study progress" className="progress-guide">
        <ol>
          {summary.steps.map((step) => (
            <li key={step.key} data-status={step.status}>
              <span>{step.label}</span>
              <small>{step.status}</small>
            </li>
          ))}
        </ol>
      </nav>

      {summary.blockers.length ? (
        <section className="blocker-panel" aria-labelledby="blockers-heading">
          <h2 id="blockers-heading">What needs attention</h2>
          <ul>
            {summary.blockers.map((blocker) => (
              <li key={blocker.code}>
                {blocker.message} <span className="finding-code">({blocker.code})</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="input-panel" aria-labelledby="inputs-heading">
        <h2 id="inputs-heading">Current inputs</h2>
        <div className="input-grid">
          <InputCard
            studyId={summary.study.id}
            role="synopsis"
            input={summary.inputs.synopsis}
            disabled={summary.readOnly || busy}
            api={api}
            onWorkspace={setSummary}
          />
          <InputCard
            studyId={summary.study.id}
            role="template"
            input={summary.inputs.template}
            disabled={summary.readOnly || busy}
            api={api}
            onWorkspace={setSummary}
          />
        </div>
      </section>

      <section className="next-action" aria-labelledby="next-action-heading">
        <div>
          <p className="eyebrow">Next safe action</p>
          <h2 id="next-action-heading">{action.label}</h2>
          <p>
            {summary.counts.candidateFacts + summary.counts.conflictedFacts} candidate facts · {summary.counts.acceptedPassages} of 4 passages accepted
          </p>
        </div>
        {action.href ? (
          <a className="primary-action" href={action.href}>{action.label}</a>
        ) : commandAction ? (
          <button type="button" disabled={busy || summary.readOnly} onClick={runCommand}>
            {busy ? "Updating…" : action.label}
          </button>
        ) : (
          <p>Use the matching input card above.</p>
        )}
      </section>
    </main>
  );
}
