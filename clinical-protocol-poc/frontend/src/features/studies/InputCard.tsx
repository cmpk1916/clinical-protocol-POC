"use client";

import React, { FormEvent, useState } from "react";

import {
  protocolWorkspaceApi,
  type InputApi,
  type ReplacementImpact,
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
  const [replacement, setReplacement] = useState<ReplacementImpact | null>(null);
  const [replacementStudyVersion, setReplacementStudyVersion] = useState<number | null>(null);
  const title = role === "synopsis" ? "Synopsis" : "Protocol template";
  const inputLabel = role === "synopsis" ? "Synopsis DOCX" : "Template DOCX";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || disabled) return;
    setBusy(true);
    setError(null);
    setFindings([]);
    setReplacement(null);
    try {
      const result = await api.uploadInput(studyId, role, file);
      setFindings(result.outcome.findings);
      onWorkspace(result.workspace);
      if (result.outcome.status === "replacement_confirmation_required" && result.outcome.version_id) {
        if (!api.previewReplacement) throw new Error("Replacement preview is unavailable");
        const preview = await api.previewReplacement({
          studyId,
          role,
          proposedVersionId: result.outcome.version_id,
        });
        setReplacement(preview);
        setReplacementStudyVersion(result.workspace.study.version);
      }
      if (result.outcome.status !== "conformance_failed") setFile(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Unable to upload ${role}`);
    } finally {
      setBusy(false);
    }
  }

  async function confirmReplacement() {
    if (!replacement || replacementStudyVersion === null || !api.confirmReplacement) return;
    setBusy(true);
    setError(null);
    try {
      const summary = await api.confirmReplacement({
        studyId,
        role,
        proposedVersionId: replacement.proposed_version_id,
        expectedCurrentVersionId: replacement.current_version_id,
        expectedStudyVersion: replacementStudyVersion,
      });
      setReplacement(null);
      onWorkspace(summary);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Unable to confirm replacement";
      if (message.includes("STUDY_VERSION_CONFLICT")) {
        try {
          const refreshed = await api.getWorkspace?.(studyId);
          if (refreshed) onWorkspace(refreshed);
        } catch {
          // The conflict message remains actionable even if the automatic refresh fails.
        }
        setError("The study changed in another window. Review the latest version before trying again.");
      } else {
        setError(message);
      }
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
      {replacement ? (
        <section aria-labelledby={`${role}-replacement-heading`}>
          <h4 id={`${role}-replacement-heading`}>Confirm replacement</h4>
          <p>
            Current: <strong>{replacement.current_filename}</strong> · Version {replacement.current_version}
          </p>
          <p>
            Proposed: <strong>{replacement.proposed_filename}</strong> · Version {replacement.proposed_version}
          </p>
          <p>This replacement will:</p>
          <ul>
            {replacement.effects.map((effect) => (
              <li key={effect}>{effect.replaceAll("_", " ")}</li>
            ))}
          </ul>
          <button type="button" disabled={busy} onClick={confirmReplacement}>
            {busy ? "Confirming replacement…" : "Confirm replacement"}
          </button>
        </section>
      ) : null}
      {error ? <p role="alert" className="error-banner">{error}</p> : null}
    </article>
  );
}
