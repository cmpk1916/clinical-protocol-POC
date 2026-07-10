import type {
  DraftPassage,
  ExportApi,
  ExportState,
  PassageApi,
  QualityScorecard,
  ReviewQueuePayload,
  StudyModel,
} from "./types";

export type ReviewApi = {
  getReviewQueue(studyId: string): Promise<ReviewQueuePayload>;
  approveFact(input: {
    studyId: string;
    factId: string;
    versionToken: string;
    explicitCriticalConfirmation: boolean;
  }): Promise<{ ok: true }>;
};

export type ModelApi = {
  getStudyModel(studyId: string): Promise<StudyModel>;
};

const reviewQueue: ReviewQueuePayload = {
  blockers: ["Export blocked: 1 critical fact requires writer confirmation"],
  items: [
    {
      id: "fact-dose",
      label: "Investigational product dose",
      category: "Intervention",
      candidateValue: "10 mg once daily",
      currentValue: "Unapproved",
      evidenceLocation: "Synopsis p. 4, Intervention paragraph 2",
      confidence: 0.91,
      downstreamImpact: ["Draft dose passage", "Traceability table", "Export gate"],
      isCritical: true,
      versionToken: "v-dose-3",
      status: "needs_review",
    },
  ],
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

export const demoReviewApi: ReviewApi = {
  async getReviewQueue() {
    return reviewQueue;
  },
  async approveFact() {
    return { ok: true };
  },
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

const successfulExport: ExportState = {
  blockers: [],
  snapshotId: "snapshot-demo-001",
  artifacts: [
    { name: "protocol.docx", sha256: "demo-docx-sha256", snapshotId: "snapshot-demo-001" },
    { name: "traceability.csv", sha256: "demo-csv-sha256", snapshotId: "snapshot-demo-001" },
    { name: "scorecard.html", sha256: "demo-html-sha256", snapshotId: "snapshot-demo-001" },
  ],
};

export const demoExportApi: ExportApi = {
  async createExport() {
    return successfulExport;
  },
};

export const demoExportState: ExportState = {
  blockers: [],
  snapshotId: null,
  artifacts: [],
};
