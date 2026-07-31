import type {
  DraftPassage,
  ExportApi,
  ExportState,
  QualityScorecard,
  ReviewQueuePayload,
  WorkspaceBlocker,
  WorkspaceInput,
  WorkspaceSummary,
} from "./types";

export type { WorkspaceSummary } from "./types";

export type ReviewApi = {
  getReviewQueue(studyId: string): Promise<ReviewQueuePayload>;
  approveFact(input: {
    studyId: string;
    factId: string;
    versionToken: string;
    explicitCriticalConfirmation: boolean;
  }): Promise<ReviewQueuePayload>;
  reviewFact(input: {
    studyId: string;
    factId: string;
    versionToken: string;
    action: "reject" | "defer" | "resume" | "resolve_conflict";
    rationale: string;
  }): Promise<ReviewQueuePayload>;
};

export type ValidationFinding = { code: string; field: string; message: string };

export type UploadOutcome = {
  status: string;
  findings: ValidationFinding[];
  version_id?: string;
};

export type ReplacementImpact = {
  role: "synopsis" | "template";
  current_version_id: string;
  current_filename: string;
  current_version: number;
  proposed_version_id: string;
  proposed_filename: string;
  proposed_version: number;
  conformance_status: string;
  effects: string[];
};

export type InputApi = {
  uploadInput(
    studyId: string,
    role: "synopsis" | "template",
    file: File,
  ): Promise<{ outcome: UploadOutcome; workspace: WorkspaceSummary }>;
  previewReplacement?(input: {
    studyId: string;
    role: "synopsis" | "template";
    proposedVersionId: string;
  }): Promise<ReplacementImpact>;
  confirmReplacement?(input: {
    studyId: string;
    role: "synopsis" | "template";
    proposedVersionId: string;
    expectedCurrentVersionId: string;
    expectedStudyVersion: number;
  }): Promise<WorkspaceSummary>;
  getWorkspace?(studyId: string): Promise<WorkspaceSummary>;
};

export type WorkspaceApi = InputApi & {
  getWorkspace(studyId: string): Promise<WorkspaceSummary>;
  processSynopsis(studyId: string, versionId: string): Promise<WorkspaceSummary>;
  retryProcessing(studyId: string, attemptId: string): Promise<WorkspaceSummary>;
};

type WorkspaceBlockerPayload = {
  code: string;
  message: string;
  affected_area: string | null;
  blocking_reason: string;
};

export type WorkspacePayload = {
  study: WorkspaceSummary["study"];
  step: WorkspaceSummary["step"];
  read_only: boolean;
  steps: WorkspaceSummary["steps"];
  counts: {
    candidate_facts: number;
    conflicted_facts: number;
    approved_facts: number;
    accepted_passages: number;
    total_passages: number;
    stale_passages: number;
    blocked_passages: number;
    rejected_passages: number;
    exports: number;
  };
  blockers: WorkspaceBlockerPayload[];
  inputs: Record<"synopsis" | "template", null | {
    role: "synopsis" | "template";
    version_id: string;
    version: number;
    filename: string;
    conformance_status: string;
  }>;
  processing: null | {
    attempt_id: string;
    status: string;
    findings: WorkspaceBlockerPayload[];
  };
  next_action: {
    kind: string;
    label: string;
    target_id: string | null;
    href: string | null;
  };
  export_command: null | {
    expected_study_version: number;
    template_version_id: string;
    template_hash: string;
  };
};

function mapInput(input: WorkspacePayload["inputs"]["synopsis"]): WorkspaceInput | null {
  return input ? {
    role: input.role,
    versionId: input.version_id,
    version: input.version,
    filename: input.filename,
    conformanceStatus: input.conformance_status,
  } : null;
}

function mapBlocker(blocker: WorkspaceBlockerPayload): WorkspaceBlocker {
  return {
    code: blocker.code,
    message: blocker.message,
    affectedArea: blocker.affected_area,
    blockingReason: blocker.blocking_reason,
  };
}

export function toWorkspaceSummary(payload: WorkspacePayload): WorkspaceSummary {
  return {
    study: payload.study,
    step: payload.step,
    readOnly: payload.read_only,
    steps: payload.steps,
    counts: {
      candidateFacts: payload.counts.candidate_facts,
      conflictedFacts: payload.counts.conflicted_facts,
      approvedFacts: payload.counts.approved_facts,
      acceptedPassages: payload.counts.accepted_passages,
      totalPassages: payload.counts.total_passages,
      stalePassages: payload.counts.stale_passages,
      blockedPassages: payload.counts.blocked_passages,
      rejectedPassages: payload.counts.rejected_passages,
      exports: payload.counts.exports,
    },
    blockers: payload.blockers.map(mapBlocker),
    inputs: {
      synopsis: mapInput(payload.inputs.synopsis),
      template: mapInput(payload.inputs.template),
    },
    processing: payload.processing ? {
      attemptId: payload.processing.attempt_id,
      status: payload.processing.status,
      findings: payload.processing.findings.map(mapBlocker),
    } : null,
    nextAction: {
      kind: payload.next_action.kind,
      label: payload.next_action.label,
      targetId: payload.next_action.target_id,
      href: payload.next_action.href,
    },
    exportCommand: payload.export_command ? {
      expectedStudyVersion: payload.export_command.expected_study_version,
      templateVersionId: payload.export_command.template_version_id,
      templateHash: payload.export_command.template_hash,
    } : null,
  };
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  const payload = await response.json().catch(() => null) as null | {
    detail?: { code?: string } | string;
  };
  if (typeof payload?.detail === "object" && payload.detail.code) return payload.detail.code;
  if (typeof payload?.detail === "string") return payload.detail;
  return fallback;
}

async function loadWorkspace(studyId: string): Promise<WorkspaceSummary> {
  const response = await fetch(`/api/local/studies/${encodeURIComponent(studyId)}/workspace`);
  if (!response.ok) throw new Error(await errorMessage(response, "Unable to load workspace"));
  return toWorkspaceSummary(await response.json() as WorkspacePayload);
}

export const protocolWorkspaceApi: WorkspaceApi = {
  getWorkspace: loadWorkspace,
  async uploadInput(studyId, role, file) {
    const form = new FormData();
    form.set("role", role);
    form.set("file", file);
    const response = await fetch(`/api/local/studies/${encodeURIComponent(studyId)}/inputs`, {
      method: "POST",
      body: form,
    });
    if (!response.ok) throw new Error(await errorMessage(response, `Unable to upload ${role}`));
    const outcome = await response.json() as UploadOutcome;
    return { outcome, workspace: await loadWorkspace(studyId) };
  },
  async processSynopsis(studyId, versionId) {
    const response = await fetch(
      `/api/local/studies/${encodeURIComponent(studyId)}/inputs/${encodeURIComponent(versionId)}/process`,
      { method: "POST" },
    );
    if (!response.ok) throw new Error(await errorMessage(response, "Unable to process synopsis"));
    return loadWorkspace(studyId);
  },
  async retryProcessing(studyId, attemptId) {
    const response = await fetch(
      `/api/local/studies/${encodeURIComponent(studyId)}/processing-attempts/${encodeURIComponent(attemptId)}/retry`,
      { method: "POST" },
    );
    if (!response.ok) throw new Error(await errorMessage(response, "Unable to retry processing"));
    return loadWorkspace(studyId);
  },
  async previewReplacement(input) {
    const response = await fetch(
      `/api/local/studies/${encodeURIComponent(input.studyId)}/inputs/${encodeURIComponent(input.role)}/replacement-preview`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposed_version_id: input.proposedVersionId }),
      },
    );
    if (!response.ok) throw new Error(await errorMessage(response, "Unable to preview replacement"));
    return await response.json() as ReplacementImpact;
  },
  async confirmReplacement(input) {
    const response = await fetch(
      `/api/local/studies/${encodeURIComponent(input.studyId)}/inputs/${encodeURIComponent(input.role)}/replacement-confirmation`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          proposed_version_id: input.proposedVersionId,
          expected_current_version_id: input.expectedCurrentVersionId,
          expected_study_version: input.expectedStudyVersion,
        }),
      },
    );
    if (!response.ok) throw new Error(await errorMessage(response, "Unable to confirm replacement"));
    return loadWorkspace(input.studyId);
  },
};

type ReviewPayload = {
  read_only: boolean;
  items: Array<{
    id: string;
    kind: string;
    status: "candidate" | "conflicted";
    deferred: boolean;
    current_value: Record<string, unknown>;
    confidence: number | null;
    source_evidence: null | { location: Record<string, unknown>; text: string };
    evidence_valid: boolean;
    critical: boolean;
    version: number;
    downstream_impact: string[];
  }>;
};

function displayValue(value: Record<string, unknown>): string {
  const parts = [value.value, value.unit, value.frequency].filter(
    (part): part is string | number => typeof part === "string" || typeof part === "number",
  );
  return parts.length ? parts.join(" ") : JSON.stringify(value);
}

function displayLocation(location: Record<string, unknown>): string {
  const kind = typeof location.kind === "string" ? location.kind : "source";
  const index = typeof location.index === "number" ? ` ${location.index + 1}` : "";
  return `${kind[0]?.toUpperCase() ?? ""}${kind.slice(1)}${index}`;
}

function mapReview(payload: ReviewPayload): ReviewQueuePayload {
  const items = payload.items.map((item): ReviewQueuePayload["items"][number] => ({
    id: item.id,
    label: item.kind.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()),
    category: item.kind,
    candidateValue: displayValue(item.current_value),
    currentValue: "Unapproved",
    evidenceLocation: item.evidence_valid && item.source_evidence
      ? displayLocation(item.source_evidence.location)
      : "",
    evidenceText: item.evidence_valid && item.source_evidence ? item.source_evidence.text : "",
    evidenceValid: item.evidence_valid && item.source_evidence !== null,
    confidence: item.confidence ?? 0,
    downstreamImpact: item.downstream_impact,
    isCritical: item.critical,
    versionToken: String(item.version),
    status: item.status === "conflicted" ? "conflict" : item.deferred ? "deferred" : "needs_review",
  }));
  const blockers = items
    .filter((item) => item.isCritical || item.status === "conflict")
    .map((item) => `${item.label} requires review before export.`)
    .concat(
      items
        .filter((item) => item.evidenceValid === false)
        .map((item) => `${item.label} is blocked because exact source evidence could not be verified.`),
    );
  return { blockers, items, readOnly: payload.read_only };
}

async function getReviewQueue(studyId: string): Promise<ReviewQueuePayload> {
  const response = await fetch(`/api/local/studies/${encodeURIComponent(studyId)}/fact-review`);
  if (!response.ok) throw new Error(await errorMessage(response, "Unable to load fact review"));
  return mapReview(await response.json() as ReviewPayload);
}

async function postReview(
  input: { studyId: string; factId: string; versionToken: string },
  body: Record<string, unknown>,
): Promise<ReviewQueuePayload> {
  const response = await fetch(`/api/local/facts/${encodeURIComponent(input.factId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_version: Number(input.versionToken), ...body }),
  });
  if (!response.ok) throw new Error(await errorMessage(response, "Unable to save fact review"));
  return getReviewQueue(input.studyId);
}

export const protocolReviewApi: ReviewApi = {
  getReviewQueue,
  approveFact(input) {
    return postReview(input, {
      action: "approve",
      explicitly_confirmed: input.explicitCriticalConfirmation,
    });
  },
  reviewFact(input) {
    return postReview(input, { action: input.action, rationale: input.rationale });
  },
};

type PassagePayload = {
  id: string;
  section: string;
  text: string;
  status: "draft" | "blocked" | "ready_for_review" | "accepted" | "rejected" | "stale";
  version: number;
  stale: boolean;
  placeholders: string[];
  findings: Array<{ code: string; message: string }>;
  fact_support_ids: string[];
  guidance_support_ids: string[];
};

type PassageListPayload = { read_only: boolean; passages: PassagePayload[] };

function mapPassage(passage: PassagePayload): DraftPassage {
  return {
    id: passage.id,
    section: passage.section.replaceAll("_", " "),
    text: passage.text,
    status: passage.status === "ready_for_review" ? "valid" : passage.status,
    version: passage.version,
    stale: passage.stale,
    findings: [
      ...passage.findings,
      ...passage.placeholders.map((message) => ({ code: "REQUIRED_FACT", message })),
    ],
    evidence: passage.fact_support_ids.map((id) => `Approved fact support: ${id}`),
    guidance: passage.guidance_support_ids,
    impact: passage.stale ? ["This passage must be regenerated before acceptance."] : [],
  };
}

async function loadPassages(studyId: string): Promise<{ readOnly: boolean; passages: DraftPassage[] }> {
  const response = await fetch(`/api/local/studies/${encodeURIComponent(studyId)}/passages`);
  if (!response.ok) throw new Error(await errorMessage(response, "Unable to load passages"));
  const payload = await response.json() as PassageListPayload;
  return { readOnly: payload.read_only, passages: payload.passages.map(mapPassage) };
}

export type DraftingApi = {
  getPassages(studyId: string): Promise<{ readOnly: boolean; passages: DraftPassage[] }>;
  getQuality(studyId: string): Promise<QualityScorecard>;
  generatePassage(input: {
    studyId: string;
    section: "synopsis" | "objectives_endpoints" | "study_design" | "eligibility";
  }): Promise<void>;
  reviewPassage(input: {
    studyId: string;
    passageId: string;
    action: "accept" | "edit" | "reject" | "regenerate";
    expectedVersion: number;
    text?: string;
    supportIds?: string[];
    rationale?: string;
  }): Promise<DraftPassage>;
};

export const protocolDraftingApi: DraftingApi = {
  getPassages: loadPassages,
  async getQuality(studyId) {
    const response = await fetch(`/api/local/studies/${encodeURIComponent(studyId)}/quality`);
    if (!response.ok) throw new Error(await errorMessage(response, "Unable to load quality state"));
    const payload = await response.json() as {
      dimensions: Record<string, { status: "pass" | "needs_review" | "blocked" | "not_applicable"; passed_count: number; finding_codes: string[] }>;
      blockers: Array<{ message: string }>;
    };
    return {
      disclaimer: "Synthetic-only, non-validated POC signal; not clinical, regulatory, or submission ready.",
      dimensions: Object.entries(payload.dimensions).map(([name, value]) => ({
        name,
        status: value.status === "pass" ? "pass" : value.status === "blocked" ? "blocked" : "warning",
        count: value.passed_count,
        findings: value.finding_codes,
      })),
    };
  },
  async generatePassage(input) {
    const response = await fetch(`/api/local/studies/${encodeURIComponent(input.studyId)}/passages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section: input.section }),
    });
    if (!response.ok) throw new Error(await errorMessage(response, "Unable to generate passage"));
  },
  async reviewPassage(input) {
    const response = await fetch(`/api/local/passages/${encodeURIComponent(input.passageId)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: input.action,
        expected_version: input.expectedVersion,
        text: input.text,
        support_ids: input.supportIds,
        rationale: input.rationale,
      }),
    });
    if (!response.ok) throw new Error(await errorMessage(response, "Unable to save passage review"));
    const refreshed = await loadPassages(input.studyId);
    const passage = refreshed.passages.find((item) => item.id === input.passageId);
    if (!passage) throw new Error("PASSAGE_NOT_FOUND_AFTER_REFRESH");
    return passage;
  },
};

function localExportState(payload: ExportState): ExportState {
  return {
    ...payload,
    artifacts: payload.artifacts.map((artifact) => ({
      ...artifact,
      downloadUrl: `/api/local/export-artifacts/${encodeURIComponent(artifact.id)}`,
    })),
  };
}

export const protocolExportApi: ExportApi = {
  async loadLatest(studyId) {
    const response = await fetch(
      `/api/local/studies/${encodeURIComponent(studyId)}/exports/latest`,
    );
    if (!response.ok) {
      throw new Error(await errorMessage(response, "Unable to load saved export"));
    }
    return localExportState((await response.json()) as ExportState);
  },
  async createExport(studyId, command) {
    const response = await fetch(`/api/local/studies/${encodeURIComponent(studyId)}/exports`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(command),
    });
    const payload = (await response.json()) as ExportState & {
      detail?: { blockers?: string[] };
    };
    if (!response.ok) {
      return {
        blockers: payload.detail?.blockers ?? ["Export failed"],
        snapshotId: null,
        artifacts: [],
      };
    }
    return localExportState(payload);
  },
};

export const demoExportState: ExportState = {
  blockers: [],
  snapshotId: null,
  artifacts: [],
};
