import type {
  DraftPassage,
  ExportApi,
  ExportState,
  PassageApi,
  QualityScorecard,
  ReviewQueuePayload,
  StudyModel,
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
};

export type InputApi = {
  uploadInput(
    studyId: string,
    role: "synopsis" | "template",
    file: File,
  ): Promise<{ outcome: UploadOutcome; workspace: WorkspaceSummary }>;
};

export type WorkspaceApi = InputApi & {
  getWorkspace(studyId: string): Promise<WorkspaceSummary>;
  processSynopsis(studyId: string, versionId: string): Promise<WorkspaceSummary>;
  retryProcessing(studyId: string, attemptId: string): Promise<WorkspaceSummary>;
};

type WorkspacePayload = {
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
  blockers: WorkspaceSummary["blockers"];
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
    findings: WorkspaceSummary["blockers"];
  };
  next_action: {
    kind: string;
    label: string;
    target_id: string | null;
    href: string | null;
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
    blockers: payload.blockers,
    inputs: {
      synopsis: mapInput(payload.inputs.synopsis),
      template: mapInput(payload.inputs.template),
    },
    processing: payload.processing ? {
      attemptId: payload.processing.attempt_id,
      status: payload.processing.status,
      findings: payload.processing.findings,
    } : null,
    nextAction: {
      kind: payload.next_action.kind,
      label: payload.next_action.label,
      targetId: payload.next_action.target_id,
      href: payload.next_action.href,
    },
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

export type ModelApi = {
  getStudyModel(studyId: string): Promise<StudyModel>;
};

const studyModel: StudyModel = {
  facts: [
    {
      id: "fact-dose",
      label: "Dose",
      value: "10 mg once daily",
      status: "approved",
      version: "v3",
      provenance: ["Synopsis p. 4"],
      conflicts: [],
      affectedPassages: ["Treatment administration"],
      relationships: [{ label: "belongs to arm", target: "Arm A" }],
    },
    {
      id: "fact-endpoint",
      label: "Primary endpoint",
      value: "Change from baseline at Week 24",
      status: "conflict",
      version: "v2",
      provenance: ["Synopsis p. 6", "CSR extract p. 2"],
      conflicts: ["Endpoint wording differs across sources"],
      affectedPassages: ["Objectives", "Endpoints"],
      relationships: [{ label: "measured at", target: "Week 24" }],
    },
  ],
};

export const demoModelApi: ModelApi = {
  async getStudyModel() {
    return studyModel;
  },
};

export const demoPassages: DraftPassage[] = [
  {
    id: "passage-dose",
    section: "Treatment administration",
    text: "Participants receive 10 mg once daily.",
    status: "valid",
    stale: false,
    findings: [],
    evidence: ["Synopsis p. 4 supports 10 mg once daily"],
    guidance: ["Draft only from approved facts."],
    impact: ["Traceability table", "Export snapshot"],
  },
];

export const demoPassageApi: PassageApi = {
  async acceptPassage() {
    return { ok: true };
  },
  async validatePassage({ text }) {
    if (text.includes("20 mg")) {
      return {
        ok: false,
        findings: [{ code: "UNSUPPORTED_CONTENT", message: "Unsupported dose: 20 mg" }],
      };
    }

    return { ok: true, findings: [] };
  },
};

export const demoScorecard: QualityScorecard = {
  disclaimer: "Dimension-level signal only; not readiness.",
  dimensions: [
    { name: "Traceability", status: "pass", count: 0, findings: [] },
    { name: "Completeness", status: "pass", count: 0, findings: [] },
    { name: "Consistency", status: "pass", count: 0, findings: [] },
    { name: "Guidance coverage", status: "pass", count: 0, findings: [] },
    { name: "Staleness", status: "pass", count: 0, findings: [] },
    { name: "Export blockers", status: "pass", count: 0, findings: [] },
  ],
};

export const protocolExportApi: ExportApi = {
  async createExport(studyId) {
    const response = await fetch(`/api/studies/${encodeURIComponent(studyId)}/exports`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
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
    return payload;
  },
};

export const demoExportState: ExportState = {
  blockers: [],
  snapshotId: null,
  artifacts: [],
};
