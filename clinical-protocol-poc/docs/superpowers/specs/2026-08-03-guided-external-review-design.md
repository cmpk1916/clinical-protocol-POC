# Guided External Review Checkpoint

**Date:** 2026-08-03  
**Status:** Approved design

## Context

The Clinical Protocol POC now supports a complete local synthetic workflow from DOCX upload through deterministic extraction, fact review, passage review, fail-closed validation, and snapshot-linked export. The six-study reliability pilot proved three direct-success journeys and three mistake-and-recovery journeys across two isolated clean stacks, with deterministic agreement and zero unsupported clinical facts exported.

That evidence is intentionally bounded. It does not establish generalization to unfamiliar study wording, layouts, values, sections, or real sponsor documents. Building a broader evaluation or protocol model without external feedback would risk optimizing for variations and workflow problems that prospective users do not consider important.

## Decision

Complete a presenter-controlled Guided External Review checkpoint before designing and implementing the Generalization and Evaluation milestone.

The checkpoint will use one shared core walkthrough with role-specific questions. Reviewers will participate virtually through screen sharing while the presenter retains control of the application. Reviewers receive no application credentials, remote-control access, repository access, installation package, or public link.

## Purpose

The checkpoint will determine:

- whether the application and its decisions are understandable;
- whether detecting, explaining, and correcting mistakes addresses a meaningful workflow problem;
- whether the protocol, traceability, and scorecard artifacts are useful;
- which document variations and failure cases belong in the next evaluation;
- which capabilities should be prioritized or deferred; and
- what evidence prospective users would require before considering a controlled design-partner pilot.

## Boundaries

The checkpoint remains local, single-presenter, deterministic, and synthetic-only.

It does not include:

- public hosting or independent reviewer access;
- remote control of the presenter's computer;
- real sponsor, patient, confidential, clinical, regulatory, or production documents;
- claims of clinical, regulatory, submission, operational, production, or system-validation readiness;
- new protocol functionality before the reviews; or
- application changes unless a defect prevents the approved walkthrough from functioning.

Any blocking application defect will be documented and handled through a separately approved repair. Reviewer feature requests are evidence, not automatic implementation commitments.

## Reviewers and Sequence

The three initial reviews occur in this order:

1. An R&D reviewer with limited protocol experience, emphasizing comprehension and guidance.
2. A reviewer with CRO experience, emphasizing operational workflow and adoption constraints.
3. A medical writer, emphasizing content quality, provenance, authoring controls, and output utility.

Every reviewer sees the same core workflows so observations remain comparable. The discussion then changes according to reviewer expertise.

## Session Structure

Each virtual session should take approximately 35 to 45 minutes.

### 1. Opening: 5 minutes

Explain that the application is a synthetic proof of concept. Describe the problem as converting source information into reviewable protocol content while preventing unsupported information from reaching export. State the synthetic-only and non-readiness boundaries before demonstrating the application.

### 2. Successful workflow: 10 to 15 minutes

Use the checked-in `fixtures/reliability-pilot/standard/` study pack and the real self-service workflow to demonstrate:

- study creation;
- synopsis and template upload;
- deterministic synopsis processing;
- fact and evidence review;
- passage generation and review;
- export creation; and
- download of `protocol.docx`, `traceability.csv`, and `scorecard.html`.

### 3. Mistake and recovery: 10 minutes

Use the checked-in `fixtures/reliability-pilot/missing-dose/` study pack and corrected synopsis to demonstrate:

- detection of missing critical dose information;
- safe workflow blocking;
- explanation of the problem and recommended correction;
- explicit versioned source replacement;
- reprocessing after correction; and
- successful continuation without silently inventing content.

### 4. Role-specific discussion: 10 to 15 minutes

Ask the shared questions first, then the questions for the reviewer's role. The presenter continues controlling the application while responding to requests to revisit screens or artifacts.

### 5. Immediate notes

Complete the feedback record immediately after the call. Separate direct observations and reviewer statements from interpretation, prioritization, and proposed product changes.

## Shared Questions

Ask every reviewer:

- What did you think the application was doing?
- Which part seemed most valuable?
- Which part was confusing or unnecessary?
- What would make you distrust the result?
- What mistakes would you expect the application to catch?
- Where would this fit, or fail to fit, in your current workflow?
- What would you need to see before recommending a controlled pilot?

Questions should remain neutral. The presenter must not explain away confusion before recording it.

## Role-Specific Questions

### R&D reviewer

- Was the guidance understandable without specialized protocol experience?
- Did the application explain why each decision was required?
- Could someone accidentally approve information they did not understand?
- Which terms, screens, or actions required more explanation?

### CRO reviewer

- Where could this reduce handoffs, duplication, or review cycles?
- Are correction, versioning, archive, and export workflows realistic?
- Which sponsor templates and document variations are common?
- Which security, audit, integration, approval, or procurement requirements would block adoption?

### Medical writer

- Were the extracted facts and their evidence accurate and usable?
- Were draft passages appropriately constrained by approved facts?
- Was passage review practical for real authoring work?
- Which sections, templates, consistency checks, and Microsoft Word capabilities are essential?
- Would the traceability output reduce work or create additional work?

## Feedback Record

Create one feedback record per reviewer with these fields:

- reviewer role and relevant experience;
- session date and duration;
- workflows demonstrated;
- direct observations;
- exact reviewer statements where wording matters;
- points of confusion;
- perceived value;
- trust or safety concerns;
- workflow mismatches;
- requested capabilities;
- document or vocabulary variations described;
- commercial or pilot interest;
- presenter's interpretation; and
- items requiring confirmation from another reviewer.

Classify each actionable observation as one or more of:

- usability problem;
- clinical-content or writing risk;
- workflow mismatch;
- missing document variation;
- missing evaluation case;
- security or compliance requirement;
- commercial opportunity; or
- future feature request.

## Prioritization

A repeated finding from multiple reviewers receives higher priority. A single serious safety, content-integrity, or confidentiality concern receives immediate attention even if no other reviewer mentions it.

Conflicting feedback remains attributed to reviewer role and context; it is not averaged into a misleading consensus. No single reviewer determines the roadmap. Every proposed Generalization and Evaluation fixture or metric must trace to an observed risk, a reviewer-described variation, or an existing documented system limitation.

Each actionable finding is assigned to exactly one primary destination:

1. Generalization and Evaluation milestone;
2. later M11 and protocol-expansion milestone;
3. later security and deployment milestone; or
4. no action until additional evidence exists.

## Preflight Checklist

Before each session:

1. Confirm the application starts and reports healthy.
2. Confirm that only synthetic demonstration data is present.
3. Confirm the standard, missing-dose, and corrected-synopsis files are available.
4. Complete the successful workflow once.
5. Complete the mistake-and-recovery workflow once.
6. Confirm all three export artifacts download and open.
7. Close unrelated windows and disable distracting notifications.
8. Prepare the shared and role-specific questions.
9. Prepare a blank feedback record.

## Safeguards and Failure Handling

- Do not upload any document supplied by a reviewer.
- Do not display confidential or real clinical information.
- Do not represent the application as validated or ready for clinical, regulatory, submission, operational, or production use.
- Do not record a session without explicit reviewer permission.
- Do not conceal or silently work around unexpected behavior.
- If the application fails, record the exact action, visible result, and impact on the walkthrough.
- A session may continue with previously generated synthetic artifacts, but the failure remains part of the feedback record.

## Deliverables

The checkpoint produces:

- one presenter walkthrough guide;
- one preflight checklist;
- one shared question set;
- three role-specific question sets;
- one reusable feedback-record template;
- three completed feedback records; and
- one synthesis that maps findings to the four roadmap destinations.

The preparation materials contain no run-specific study identifiers, exported clinical claims, confidential information, or readiness claims.

## Completion Criteria

The checkpoint is complete when:

- all three reviewers have seen the same successful and mistake-and-recovery workflows;
- a feedback record is complete for each review;
- observations are separated from interpretations and feature requests;
- common findings and role-specific differences are summarized;
- every actionable finding has a primary roadmap destination;
- any demonstration failure is retained as evidence; and
- the synthesis provides enough specific evidence to define the scope, variations, metrics, and acceptance criteria for Generalization and Evaluation.

## Relationship to the Build Roadmap

This checkpoint is an evidence-gathering gate, not a replacement for the next software milestone. After it is complete, the project will design the Generalization and Evaluation milestone using the reviewer evidence. That milestone should precede M11 model expansion, broader protocol drafting, secure multiuser deployment, and any controlled use with real-world documents.
