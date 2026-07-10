# AI-Powered Clinical-Trial Protocol Creation POC

## Design Specification

**Status:** Approved  
**Version:** 1.0  
**Date:** 2026-07-02  
**Decision gate:** Approved by the user on 2026-07-02; implementation planning is authorized, but implementation remains gated on plan review.

## 1. Executive Summary

This proof of concept (POC) helps medical writers create a usable first draft of selected sections of a pharmaceutical clinical-trial protocol from a study synopsis and a Word protocol template. It is designed to reduce drafting time, manual formatting, internal inconsistencies, and revision cycles while preserving strong, explicit human oversight.

The POC uses a closed-world, fail-closed architecture. Clinical facts may enter approved protocol content only through writer-approved fields in a canonical study model. Drafted factual statements must be traceable to those approved facts. Missing, ambiguous, contradictory, or unsupported information is surfaced as a question, placeholder, warning, or blocker; it is never silently inferred. Export is prohibited until all hard quality gates pass.

The system does not make autonomous scientific, medical, or regulatory decisions and does not claim that a protocol or trial is clinically, regulatorily, submission, or operationally ready.

## 2. Product Goal and Success Definition

### 2.1 Goal

Build a POC that helps a medical writer produce a reviewable protocol first draft faster and with fewer formatting errors, inconsistencies, and revision cycles.

### 2.2 Primary user

The primary user is a medical writer preparing a protocol draft for a synthetic Phase II type 2 diabetes study.

### 2.3 Core success condition

The POC succeeds only if it can produce the scoped deliverables while exporting **zero unsupported clinical facts** in the defined evaluation suite.

### 2.4 Intended benefits

- Faster creation of a structured, usable first draft.
- Less manual transfer of synopsis facts into protocol sections.
- Less manual Word formatting.
- Earlier detection of missing facts, contradictions, and cross-section inconsistencies.
- Clear traceability from protocol statements to writer-approved source facts.
- Focused review by exception rather than undifferentiated document review.

## 3. Scope

### 3.1 In scope

- One synthetic Phase II type 2 diabetes study.
- A medical writer as the primary user.
- Inputs:
  - Study synopsis.
  - Word protocol template.
- Governed knowledge:
  - Uploaded materials.
  - Curated, version-controlled guidance library.
- Authoring outputs:
  - Structured protocol outline.
  - Drafted synopsis section.
  - Drafted objectives and endpoints section.
  - Drafted study design section.
  - Drafted eligibility section.
- Deliverables:
  - Deterministically rendered Word document.
  - Statement-level traceability report.
  - Protocol Quality and Readiness Scorecard.
- Writer review, editing, approval, rejection, and targeted regeneration.
- Append-only audit history for material actions and state changes.

### 3.2 Out of scope

- Full protocol generation.
- Confidential sponsor documents or production clinical data.
- Autonomous scientific, clinical, medical, or regulatory decisions.
- Multi-user approval workflows.
- Electronic signatures.
- 21 CFR Part 11 compliance or validated-system claims.
- Submission-readiness, regulatory-readiness, or clinical-readiness claims.
- Complete ICH M11 CeSHarP conformance claims.
- Live internet research during protocol drafting.
- Automatic learning from individual writer edits.
- Cross-tenant reuse of sponsor- or organization-specific content.

## 4. Design Principles and Safety Invariants

### 4.1 Closed-world authoring

The system drafts factual protocol content only from:

1. Writer-approved facts in the canonical study model.
2. Approved, versioned guidance and reusable patterns that are appropriate to the task.

The absence of a fact is not evidence for a default or likely value.

### 4.2 Fail-closed behavior

If the system cannot establish support, consistency, and provenance for clinical content, it must prevent that content from being approved or exported. Service errors, model uncertainty, malformed output, incomplete checks, or unavailable evidence must not degrade into permissive behavior.

### 4.3 Non-negotiable invariant

> No unsupported clinical content may be approved or exported.

This invariant is enforced in application logic and deterministic validation. Prompt instructions are defense in depth, not the primary control.

### 4.4 Explicit handling of uncertainty

- Missing information becomes a visible placeholder or writer question.
- Ambiguous information is presented for resolution and remains unapproved.
- Contradictory information is represented as a conflict and blocks affected content.
- AI recommendations remain isolated and visibly labeled as unsupported suggestions until a writer explicitly converts them into approved facts through the governed fact-review workflow.

### 4.5 Independent verification

The drafting model cannot certify its own output. Independent controls validate:

- Schema conformance.
- Provenance coverage.
- Exact clinical facts.
- Cross-section consistency.
- Approval and review state.
- Template and rendering requirements.

### 4.6 Deterministic verification targets

At minimum, deterministic checks cover:

- Doses and dose units.
- Numeric values and ranges.
- Endpoints and endpoint hierarchy.
- Timepoints and assessment windows.
- Treatment arms and intervention-to-arm mappings.
- Population definitions.
- Inclusion and exclusion criteria.
- Safety-related facts represented in the approved study model.

## 5. Content-State Model

The system keeps four content classes logically and operationally separate:

1. **Source evidence** — immutable or versioned excerpts and structured observations from uploaded materials, each with precise source location.
2. **Writer-approved study facts** — normalized facts explicitly confirmed by the writer and stored in the canonical study model.
3. **Unapproved AI suggestions** — clearly labeled recommendations or candidate language that cannot support approved content or export.
4. **Writer-accepted protocol content** — drafted or edited passages accepted by the writer and still valid against their supporting approved facts and guidance versions.

No state transition is implicit. Each approval, rejection, edit, invalidation, or revalidation is recorded in the audit trail.

### 5.1 Required transition rules

- Extracted candidates begin as source-linked observations, not approved facts.
- Critical facts always require explicit writer confirmation.
- A writer may approve, correct, reject, or defer an extracted candidate.
- A suggestion becomes usable as a clinical fact only after explicit writer entry or acceptance into the fact-review workflow, with provenance and required review checks.
- A drafted passage begins unaccepted.
- A passage may be accepted only when every factual claim is supported by approved facts and all applicable checks pass.
- Editing an approved fact invalidates every dependent accepted passage until it is reviewed and revalidated.
- Updating guidance invalidates dependent passages only when the applicability or meaning of the cited guidance has changed; the impact must be shown explicitly.
- Export uses a single consistent snapshot of approved facts, accepted passages, guidance versions, validation results, and template version.

## 6. End-to-End Workflow

### 6.1 Ingest

The writer uploads a study synopsis and Word protocol template. The system records file identity, version, checksum, upload event, and processing status. Files are treated as untrusted input.

### 6.2 Extract evidence and candidate facts

Narrow, schema-constrained extraction tasks identify candidate study facts and preserve source locations such as document, section, page, table, paragraph, or cell as available. Extraction must not confer approval.

### 6.3 Verify facts

Guided Review presents extracted candidates by exception, prioritizing critical, conflicting, ambiguous, missing, and low-confidence items. Critical facts require explicit confirmation even when confidence is high.

### 6.4 Build the canonical study model

Writer-approved facts are normalized into the relational canonical model. Model-level validation checks required fields, types, units, enumerations, cardinalities, and cross-entity relationships.

### 6.5 Retrieve approved guidance

The system searches only the curated, approved, version-controlled guidance index and approved reusable protocol patterns. Retrieval results preserve source identity, version, location, and applicability metadata. Live internet access is not available to drafting tasks.

### 6.6 Draft scoped sections

The AI gateway supplies the drafting model with only the approved study facts, applicable approved guidance, approved reusable patterns, section instructions, and required output schema. Drafting occurs in small passage-level units. Each factual claim must include machine-checkable support links.

### 6.7 Validate independently

Independent validators check schema, provenance, exact fact use, contradictions, model relationships, required placeholders, and approval state. Semantic review may identify potential issues but cannot override deterministic blockers.

### 6.8 Writer review

The writer reviews passages with supporting evidence and impact context. The writer can accept, edit, reject, or regenerate individual passages. Edited content undergoes the same claim mapping and validation as generated content.

### 6.9 Render and export

The renderer maps accepted content into the uploaded Word template through deterministic placement and style rules. Export is allowed only from a validated snapshot after every hard gate passes. The Word document, traceability report, and scorecard share the same snapshot identifier.

## 7. Writer Experience

### 7.1 Guided Review

Guided Review is the default interface. It minimizes review burden by foregrounding exceptions while never hiding warnings or blockers. It includes:

- Review queue grouped by criticality and downstream impact.
- Side-by-side source evidence and candidate fact.
- Explicit approve, edit, reject, and defer actions.
- Conflict and ambiguity resolution.
- Required confirmation for critical facts.
- Visible completion state and unresolved blockers.

### 7.2 Model Explorer

Model Explorer exposes:

- Canonical entities and relationships.
- Fact provenance and exact source location.
- Approval state and reviewer action history.
- Extraction confidence as an aid, never an approval substitute.
- Conflicts and unresolved questions.
- Version history.
- Downstream passages and deliverables affected by each fact.

### 7.3 Drafting workspace

The drafting workspace includes:

- Protocol section navigation.
- Passage-oriented document editor.
- Evidence and guidance panel.
- Claim-to-fact traceability view.
- Warnings and blockers that remain visible.
- Change-impact display.
- Passage-level accept, edit, reject, and regenerate controls.

### 7.4 Invalidation experience

When a fact changes, the interface immediately marks dependent accepted passages stale, explains why, lists affected sections and deliverables, and prevents export until affected passages are reviewed and validated again.

## 8. Canonical Study Model

The canonical model is the sole approved clinical-fact source for drafting. It covers the following domains.

### 8.1 Core entities

- **Study identity:** protocol identifier, title, phase, indication, sponsor placeholder if applicable, version, and date.
- **Rationale:** study background and rationale facts supported by source evidence.
- **Objectives:** primary, secondary, and exploratory objectives.
- **Endpoints:** endpoint definition, hierarchy, linked objective, measure, aggregation, timepoint/window, and analysis population where specified.
- **Study design:** design type, randomization, blinding, control, duration, visits or periods at the POC level, and planned enrollment.
- **Population:** condition, demographic or disease characteristics, analysis or treatment populations where specified.
- **Arms:** arm identity, role, allocation, and linked interventions.
- **Interventions:** product or control, dose, unit, route, frequency, regimen, and duration where specified.
- **Eligibility criteria:** inclusion/exclusion type, criterion text or structured elements, applicability, and linked population.
- **Key schedule concepts:** periods, visits, timepoints, and assessment timing needed for the scoped sections.
- **Protocol passages:** section, text, review state, validation state, supporting facts, supporting guidance, version, and invalidation status.

### 8.2 Explicit relationships

- Endpoint → objective.
- Endpoint → timepoint or window.
- Endpoint → applicable population, when specified.
- Intervention → arm.
- Eligibility criterion → population.
- Passage claim → approved fact(s).
- Passage → approved guidance or reusable pattern, where used.
- Fact → source evidence.
- Fact change → affected passage(s) and deliverable(s).

### 8.3 Fact metadata

Each fact records:

- Stable identifier.
- Typed value and unit where applicable.
- Source evidence identifier and location.
- Approval status.
- Approving writer action and timestamp.
- Version and supersession relationship.
- Conflict and ambiguity status.
- Criticality classification.
- Downstream dependencies.

## 9. Provenance and Claim Control

### 9.1 Statement-level support

Every factual statement in writer-accepted content must be decomposable into one or more claims. Each claim maps to one or more current, writer-approved facts. A passage cannot be accepted if any clinical claim lacks complete support.

### 9.2 Support rules

- Guidance can govern structure or phrasing but cannot supply study-specific clinical facts.
- Reusable patterns cannot silently introduce study-specific values or assumptions.
- A citation to a source document alone is insufficient; the relevant source evidence must have been converted into an approved fact.
- Free-text writer edits must pass claim extraction and deterministic fact comparison before acceptance.
- If claim boundaries or support mappings are uncertain, the passage remains blocked for review.

### 9.3 Traceability report

The report is generated from the export snapshot and includes:

- Deliverable and snapshot identifiers.
- Section and passage identifiers.
- Factual claims.
- Supporting approved fact identifiers and values.
- Original source document and location.
- Applicable guidance source and version.
- Writer review state.
- Validation status and relevant findings.
- Fact, passage, guidance, and template versions.

## 10. Quality and Readiness Scorecard

The scorecard reports evidence about the draft; it does not certify the protocol or trial as ready. It must use plain, bounded status language and must not present a misleading composite percentage.

### 10.1 Hard blockers

Export is blocked by any of the following:

- Unsupported content.
- Unresolved critical facts.
- Critical contradictions.
- Incomplete provenance.
- Required placeholders.
- Incomplete or failed mandatory validation.
- Stale accepted passages caused by changed facts or governed sources.

### 10.2 Separately reported dimensions

- **Completeness:** required scoped fields and sections populated or explicitly resolved.
- **Consistency:** deterministic and semantic checks across facts, relationships, and passages.
- **Traceability:** claims fully mapped through approved facts to source evidence.
- **Template conformance:** expected sections, styles, locations, and rendering rules satisfied.
- **Writer-review status:** required facts and passages explicitly reviewed.
- **Approved-guidance coverage:** applicable approved guidance considered and linked where required.

Each dimension reports status, counts, affected items, and actionable findings. Suggested labels are `Pass`, `Needs review`, `Blocked`, and `Not applicable`; percentages may be used only for transparent counts within a dimension and never as an overall readiness score.

## 11. Technical Architecture

### 11.1 Architectural style

Use a modular monolith for the POC, with clear internal module boundaries and a small number of deployable components. This reduces operational complexity while preserving separable domains for future evolution.

### 11.2 Technology direction

- **Frontend:** React with Next.js.
- **Backend:** Python web application/API.
- **Database:** relational database for canonical entities, workflow state, versions, relationships, and findings.
- **File storage:** source documents, templates, rendered artifacts, and immutable snapshot artifacts.
- **Guidance search index:** approved and versioned content only.
- **AI gateway:** controlled access to model tasks, schemas, prompt versions, inputs, outputs, and policy checks.
- **Word renderer:** deterministic template population and style application.
- **Audit trail:** append-only record of material user, system, and model events.

### 11.3 Logical modules

- Identity and tenant context.
- Document ingestion and safe parsing.
- Evidence extraction.
- Fact review and canonical study model.
- Guidance governance and retrieval.
- AI orchestration gateway.
- Draft authoring and passage lifecycle.
- Validation and findings.
- Impact analysis and invalidation.
- Template mapping and Word rendering.
- Export snapshot and artifact generation.
- Scorecard and traceability reporting.
- Audit and observability.

### 11.4 Core storage boundaries

- Relational records are authoritative for workflow and canonical state.
- Object/file storage holds originals and generated artifacts with checksums and immutable version references.
- The guidance index is derived from approved guidance releases and can be rebuilt; it is not the authoritative record.
- Model prompts and responses are captured with appropriate minimization for reproducibility and evaluation, subject to tenant isolation.

### 11.5 Tenant isolation

Organization and sponsor data are partitioned by tenant throughout storage, retrieval, caching, AI requests, logs, and evaluation datasets. Sponsor-specific content is never promoted to a shared pattern or reused across tenants. The POC uses synthetic, non-confidential data only, but the boundary is retained in the design.

## 12. AI Pipeline and Controls

### 12.1 Task decomposition

Use narrow, schema-constrained model tasks for:

- Evidence and candidate-fact extraction.
- Approved-guidance retrieval support or ranking.
- Passage drafting.
- Claim identification and support-map proposal.
- Semantic consistency review.
- Human-readable explanations of deterministic findings.

### 12.2 AI gateway responsibilities

- Permit only approved task types and model configurations.
- Construct task-specific, minimal input contexts.
- Enforce structured output schemas.
- Record model, configuration, prompt version, inputs, outputs, and timestamps.
- Reject malformed, incomplete, or policy-violating outputs.
- Prevent drafting tasks from accessing unapproved evidence or suggestions as factual context.
- Disable network tools and live internet research in the drafting path.
- Treat uploaded document instructions as data, not executable instructions.

### 12.3 Independent control layers

1. Input allowlisting and state-based context assembly.
2. Structured schema validation.
3. Deterministic clinical fact comparison.
4. Provenance completeness validation.
5. Relationship and cross-section consistency checks.
6. Independent semantic review for issues not captured deterministically.
7. Writer acceptance.
8. Export-time revalidation against an immutable snapshot.

The semantic reviewer may raise findings but may not waive deterministic failures.

## 13. Deterministic Word Rendering

The renderer must not ask a language model to manipulate the final Word document. It uses explicit template mappings and reproducible rules to:

- Locate required sections and insertion points.
- Populate only scoped sections.
- Preserve approved template styles, numbering, headers, footers, and unaffected content.
- Render placeholders and blocker indicators in non-exportable previews.
- Produce stable output for the same validated snapshot and renderer version.
- Validate required sections, styles, and content placement.

Unsupported template structures or ambiguous insertion points block final export and require explicit mapping resolution.

## 14. Auditability and Versioning

The append-only audit trail records at minimum:

- File upload, parse, and version events.
- Candidate-fact extraction and source links.
- Fact approval, edit, rejection, and supersession.
- Conflict creation and resolution.
- Guidance release, retrieval, and use.
- Model task type, configuration, prompt version, result status, and validation outcome.
- Passage generation, edit, acceptance, rejection, regeneration, invalidation, and revalidation.
- Findings opened, resolved, waived where permitted, and by whom. Hard safety blockers cannot be waived for export.
- Export attempts, gate results, snapshot creation, and artifact checksums.

Audit records are not updated in place. Corrections create new events and superseding versions.

## 15. Guidance and Governed Learning

### 15.1 Governed content layers

1. **Authoritative guidance** — curated external or internal guidance with provenance, applicability, approval, effective version, and retirement state.
2. **Approved reusable protocol patterns** — reviewed structural or linguistic patterns that contain no hidden sponsor-specific facts.
3. **De-identified evaluation feedback** — approved examples and findings used for offline evaluation, not live automatic learning.

### 15.2 Promotion workflow

No system behavior or shared content changes automatically from a writer edit. Candidate improvements follow:

`Writer feedback → de-identification → domain review → approval → versioned release`

Each release is traceable and reversible through version selection. Sponsor-specific content is ineligible for cross-tenant promotion.

### 15.3 Standards direction

The information structure and template direction conceptually align with ICH M11 CeSHarP where useful. The POC must state that this is directional alignment and must not claim complete conformance.

## 16. Security and Trust Boundaries

- Use synthetic, non-confidential data only.
- Treat uploaded documents, template fields, metadata, and retrieved text as untrusted content.
- Isolate instructions in uploaded content from system and task instructions.
- Apply file type, size, malware, and parser-safety controls appropriate to the POC environment.
- Use least-privilege access between application modules and stores.
- Avoid placing clinical content in unnecessary logs or error telemetry.
- Include tenant and snapshot identifiers in authorization checks, not merely UI filters.
- Make all export decisions server-side through the validation gate.

## 17. Failure Handling

- Parsing failure produces a visible processing error and prevents affected facts from entering review.
- Model timeout or malformed output leaves the task incomplete; it does not create candidate facts or passages.
- Guidance index failure blocks tasks that require guidance and identifies the unavailable dependency.
- Validation service failure blocks acceptance/export because successful validation cannot be established.
- Rendering failure produces no final artifact and preserves the validated source snapshot for retry.
- Partial multi-step operations use durable states and idempotent retries to avoid duplicate facts, passages, or exports.

## 18. POC Evaluation Strategy

### 18.1 Reference set

Use a medical-writer-approved synthetic gold standard containing:

- Approved source synopsis and Word template.
- Expected canonical facts and relationships.
- Expected scoped section content or acceptable content criteria.
- Expected traceability mappings.
- Expected warnings and blockers for adversarial variants.

### 18.2 Required challenge cases

- Missing dose.
- Contradictory endpoints.
- Ambiguous timepoints.
- Unsupported eligibility criterion.
- Irrelevant guidance retrieval.
- Prompt injection embedded in uploaded content.
- Plausible but absent clinical facts.

Additional coverage should include changed-fact invalidation, stale guidance, malformed model output, rendering ambiguity, and validator unavailability.

### 18.3 Required safety result

Across the defined evaluation suite, final exports must contain **zero unsupported clinical facts**.

Any unsupported exported clinical fact is a release-blocking failure, not an averaged metric.

### 18.4 Supporting evaluation measures

- Fact extraction precision and recall before writer review.
- Critical-fact confirmation coverage.
- Claim-to-fact mapping completeness.
- Deterministic contradiction detection coverage.
- Required blocker detection rate.
- False-positive review burden.
- Template conformance.
- Writer time to first usable scoped draft.
- Number and type of manual corrections.
- Writer-rated usefulness and trust in explanations.

## 19. POC Acceptance Criteria

The POC is acceptable for demonstration/evaluation when all of the following are true:

1. It ingests the synthetic synopsis and Word template and preserves file versions and source locations.
2. It extracts candidate facts without treating them as approved.
3. It requires explicit writer confirmation for all critical facts.
4. It stores approved facts and required relationships in the canonical study model.
5. It drafts only the scoped sections using approved facts and approved governed content.
6. Every accepted clinical claim maps to current approved facts and source evidence.
7. Writer edits pass the same support and consistency controls as generated text.
8. Changing an approved fact invalidates every affected accepted passage and blocks export until re-review.
9. Independent deterministic checks cover the enumerated clinical fact categories.
10. The scorecard reports separate dimensions and hard blockers without a composite readiness percentage or readiness claim.
11. The Word output is deterministically populated into the approved template.
12. The Word document, traceability report, and scorecard come from one validated export snapshot.
13. Export remains blocked for every defined hard-blocker condition and when mandatory checks are unavailable.
14. The append-only audit trail reconstructs the material lineage and review history of an export.
15. The challenge suite, including prompt injection and plausible-but-absent facts, results in zero unsupported clinical facts in exports.

## 20. Assumptions and Constraints

- The POC uses one approved synthetic study package and a bounded template family.
- A qualified medical writer is available to approve the gold standard and perform user evaluation.
- Guidance is curated and approved before use; the POC does not establish the organization's governance authority.
- The POC demonstrates safety-oriented controls but is not a validated regulated system.
- The exact database, model provider, deployment environment, and Word templating library are implementation-plan decisions, subject to this design's boundaries.
- User authentication may be simplified for the POC, but tenant context and authorization boundaries must remain explicit in the data and service design.

## 21. Design Decisions Requiring Confirmation at This Gate

Approval of this specification confirms the following decisions:

- The closed-world, fail-closed safety invariant governs all clinical content.
- The canonical study model, not source text or model output, is the factual drafting authority.
- The four content states remain separated with explicit transitions.
- Critical facts and all accepted passages require human review as defined.
- Export is a server-side gated operation over an immutable, consistently versioned snapshot.
- The drafting model cannot certify its own output.
- The scorecard uses separate dimensions and makes no readiness claim.
- The POC is limited to the named sections, synthetic study, and bounded template/guidance set.
- ICH M11 CeSHarP is a conceptual direction, not a conformance claim.

## 22. Post-Approval Gate

After the user approves this design specification, the next step is to create a detailed implementation plan using the Superpowers planning workflow. No implementation work begins until that plan is separately reviewed as requested.
