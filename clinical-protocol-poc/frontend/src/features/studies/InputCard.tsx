"use client";

import React, { FormEvent, useState } from "react";

import {
  protocolWorkspaceApi,
  type InputApi,
  type ValidationFinding,
} from "../../lib/api";
import type { WorkspaceInput, WorkspaceSummary } from "../../lib/types";

type Props = {
  studyId: string;
  role: "synopsis" | "template";
  input: WorkspaceInput | null;
  disabled: boolean;
  api?: InputApi;
  onWorkspace(summary: WorkspaceSummary): void;
};

export function InputCard({
  studyId,
  role,
  input,
  disabled,
  api = protocolWorkspaceApi,
  onWorkspace,
}: Readonly<Props>) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [findings, setFindings] = useState<ValidationFinding[]>([]);
  const [error, setError] = useState<string | null>(null);
  const title = role === "synopsis" ? "Synopsis" : "Protocol template";
  const inputLabel = role === "synopsis" ? "Synopsis DOCX" : "Template DOCX";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || disabled) return;
    setBusy(true);
    setError(null);
    setFindings([]);
    try {
      const result = await api.uploadInput(studyId, role, file);
      setFindings(result.outcome.findings);
      onWorkspace(result.workspace);
      if (result.outcome.status !== "conformance_failed") setFile(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Unable to upload ${role}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="input-card" aria-labelledby={`${role}-input-heading`}>
      <div>
        <p className="status">{input ? "Current input" : "Required input"}</p>
        <h3 id={`${role}-input-heading`}>{title}</h3>
        {input ? (
          <p><strong>{input.filename}</strong> · Version {input.version} · {input.conformanceStatus}</p>
        ) : (
          <p>Upload a supported {role} DOCX. Only synthetic evaluation content is allowed.</p>
        )}
      </div>
      <form onSubmit={submit}>
        <label htmlFor={`${role}-file`}>{inputLabel}</label>
        <input
          id={`${role}-file`}
          type="file"
          accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          disabled={disabled || busy}
          onChange={(event) => setFile(event.currentTarget.files?.[0] ?? null)}
        />
        <button type="submit" disabled={disabled || busy || !file}>
          {busy ? `Uploading ${role}…` : `Upload ${role}`}
        </button>
      </form>
      {findings.length ? (
        <section aria-labelledby={`${role}-findings-heading`}>
          <h4 id={`${role}-findings-heading`}>Validation findings</h4>
          <ul>
            {findings.map((finding) => (
              <li key={`${finding.code}-${finding.field}`}>
                {finding.message} <span className="finding-code">({finding.code})</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {error ? <p role="alert" className="error-banner">{error}</p> : null}
    </article>
  );
}
