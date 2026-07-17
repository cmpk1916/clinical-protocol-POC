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
  confidence: number;
  downstreamImpact: string[];
  isCritical: boolean;
  versionToken: string;
  status: ReviewStatus;
};

export type ReviewQueuePayload = {
  blockers: string[];
  items: ReviewItem[];
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
  status: "valid" | "blocked" | "accepted" | "stale";
  stale: boolean;
  findings: PassageFinding[];
  evidence: string[];
  guidance: string[];
  impact: string[];
};

export type PassageApi = {
  acceptPassage(input: { passageId: string; text: string }): Promise<{ ok: true }>;
  validatePassage(input: {
    passageId: string;
    text: string;
  }): Promise<{ ok: boolean; findings: PassageFinding[] }>;
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
  createExport(studyId: string): Promise<ExportState>;
};
