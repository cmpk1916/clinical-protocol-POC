export type ReviewStatus = "needs_review" | "approved" | "rejected" | "deferred" | "conflict";

export type StudySummary = {
  id: string;
  name: string;
  version: number;
  lifecycle: "active" | "archived";
  updatedAt: string;
  archivedAt: string | null;
};

export type ReviewItem = {
  id: string;
  label: string;
  category: string;
  candidateValue: string;
  currentValue: string;
  evidenceLocation: string;
  evidenceText: string;
  evidenceValid?: boolean;
  confidence: number;
  downstreamImpact: string[];
  isCritical: boolean;
  versionToken: string;
  status: ReviewStatus;
};

export type WorkspaceStep = "archived" | "inputs" | "processing" | "fact_review" | "passage_review" | "export";

export type WorkspaceInput = {
  role: "synopsis" | "template";
  versionId: string;
  version: number;
  filename: string;
  conformanceStatus: string;
};

export type WorkspaceBlocker = { code: string; message: string };

export type ExportCommand = {
  expectedStudyVersion: number;
  templateVersionId: string;
  templateHash: string;
};

export type WorkspaceSummary = {
  study: {
    id: string;
    name: string;
    lifecycle: "active" | "archived";
    version: number;
  };
  step: WorkspaceStep;
  readOnly: boolean;
  steps: Array<{
    key: string;
    label: string;
    status: "complete" | "current" | "blocked" | "upcoming";
  }>;
  counts: {
    candidateFacts: number;
    conflictedFacts: number;
    approvedFacts: number;
    acceptedPassages: number;
    totalPassages: number;
    stalePassages?: number;
    blockedPassages?: number;
    rejectedPassages?: number;
    exports: number;
  };
  blockers: WorkspaceBlocker[];
  inputs: Record<"synopsis" | "template", WorkspaceInput | null>;
  processing: null | {
    attemptId: string;
    status: string;
    findings: WorkspaceBlocker[];
  };
  nextAction: {
    kind: string;
    label: string;
    targetId: string | null;
    href: string | null;
  };
  exportCommand: ExportCommand | null;
};

export type ReviewQueuePayload = {
  blockers: string[];
  items: ReviewItem[];
  readOnly?: boolean;
};

export type FactRelationship = {
  label: string;
  target: string;
};

export type ModelFact = {
  id: string;
  label: string;
  value: string;
  status: ReviewStatus;
  version: string;
  provenance: string[];
  conflicts: string[];
  affectedPassages: string[];
  relationships: FactRelationship[];
};

export type StudyModel = {
  facts: ModelFact[];
};

export type PassageFinding = {
  code: string;
  message: string;
};

export type DraftPassage = {
  id: string;
  section: string;
  text: string;
  status: "valid" | "blocked" | "accepted" | "stale" | "rejected" | "draft";
  version?: number;
  stale: boolean;
  findings: PassageFinding[];
  evidence: string[];
  guidance: string[];
  impact: string[];
};

export type PassageApi = {
  reviewPassage?: (input: {
    passageId: string;
    action: "accept" | "edit" | "reject" | "regenerate";
    expectedVersion: number;
    text?: string;
    supportIds?: string[];
    rationale?: string;
  }) => Promise<DraftPassage>;
  acceptPassage?: (input: { passageId: string; text: string }) => Promise<{ ok: true }>;
  validatePassage?: (input: {
    passageId: string;
    text: string;
  }) => Promise<{ ok: boolean; findings: PassageFinding[] }>;
};

export type QualityDimension = {
  name: string;
  status: "pass" | "warning" | "blocked";
  count: number;
  findings: string[];
};

export type QualityScorecard = {
  disclaimer: string;
  dimensions: QualityDimension[];
};

export type ExportArtifact = {
  id: string;
  name: string;
  mediaType: string;
  sha256: string;
  snapshotId: string;
  downloadUrl: string;
};

export type ExportState = {
  blockers: string[];
  snapshotId: string | null;
  artifacts: ExportArtifact[];
};

export type ExportApi = {
  createExport(studyId: string, command: ExportCommand): Promise<ExportState>;
};
