# Guided External Review Checkpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a presenter-controlled, synthetic-only review kit that produces comparable feedback from an R&D reviewer, a CRO reviewer, and a medical writer before the Generalization and Evaluation milestone is designed.

**Architecture:** Keep the application unchanged and add a focused documentation kit under `docs/guided-review/`. Executable documentation controls verify the approved workflows, questions, safeguards, classifications, and roadmap destinations. Completed reviewer records remain under ignored `work/guided-review/`; only a later sanitized synthesis may be retained in the repository.

**Tech Stack:** Markdown, Python 3.12, pytest, existing deterministic DOCX fixtures, Docker Compose, existing FastAPI/Next.js application

## Global Constraints

- The review is virtual and presenter-controlled; reviewers receive no remote control, credentials, repository access, installation package, or public link.
- Use only checked-in synthetic fixtures. Do not upload sponsor, patient, confidential, clinical, regulatory, or production documents.
- Demonstrate the real self-service workflow with `fixtures/reliability-pilot/standard/` and `fixtures/reliability-pilot/missing-dose/`.
- State that the application is a synthetic proof of concept and does not establish clinical, regulatory, submission, operational, production, or system-validation readiness.
- Do not change application behavior during this checkpoint. A blocking defect requires a separately approved repair.
- Do not record a review without explicit reviewer permission.
- Preserve direct observations separately from interpretation and feature requests.
- Store completed reviewer records only under ignored `work/guided-review/`.
- Do not retain reviewer names, employers, contact details, confidential information, or attributable quotations in a checked-in synthesis.

---

### Task 1: Local-Only Review Workspace and Documentation Contract

**Files:**
- Modify: `.gitignore`
- Create: `clinical-protocol-poc/docs/guided-review/README.md`
- Modify: `clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py`

**Interfaces:**
- Consumes: the approved Guided External Review design and the repository's existing documentation-control test pattern.
- Produces: the checked-in `docs/guided-review/` entrypoint and an ignored `work/guided-review/` location for completed records.

- [ ] **Step 1: Write the failing documentation-control test**

Append this test to `backend/tests/evaluation/test_documented_controls.py`:

```python
def test_guided_review_workspace_is_documented_and_local_only() -> None:
    app_root = Path(__file__).parents[3]
    repository_root = app_root.parent
    review_readme = (app_root / "docs" / "guided-review" / "README.md").read_text()
    gitignore = (repository_root / ".gitignore").read_text()

    required = {
        "presenter-controlled virtual review",
        "synthetic proof of concept",
        "fixtures/reliability-pilot/standard/",
        "fixtures/reliability-pilot/missing-dose/",
        "work/guided-review/",
        "completed reviewer records remain local",
        "no public link",
        "no remote control",
    }

    assert all(item in review_readme for item in required)
    assert "clinical-protocol-poc/work/guided-review/" in gitignore
```

- [ ] **Step 2: Run the test and verify the missing-kit failure**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py::test_guided_review_workspace_is_documented_and_local_only -v
```

Expected: FAIL because `docs/guided-review/README.md` does not exist.

- [ ] **Step 3: Ignore completed local reviewer records**

Add this exact entry to the repository-root `.gitignore`:

```gitignore
clinical-protocol-poc/work/guided-review/
```

- [ ] **Step 4: Create the review-kit entrypoint**

Create `docs/guided-review/README.md` with this content:

```markdown
# Guided External Review Kit

This kit supports a presenter-controlled virtual review of the Clinical Protocol POC. The presenter runs and controls the local application while each reviewer watches through screen sharing, asks questions, and requests that screens or artifacts be revisited.

The application is a synthetic proof of concept. It is not validated and does not establish clinical, regulatory, submission, operational, or production readiness.

## Demonstration studies

- Successful workflow: `fixtures/reliability-pilot/standard/`
- Mistake and recovery: `fixtures/reliability-pilot/missing-dose/`

Use only these checked-in synthetic materials. Do not upload documents supplied by a reviewer.

## Kit

- `presenter-guide.md`: session order and narration
- `preflight-checklist.md`: checks completed before every call
- `questions.md`: shared and role-specific questions
- `feedback-template.md`: local record for one review
- `synthesis-template.md`: comparison and roadmap decisions after all three reviews

## Access boundary

Reviewers receive no public link, no remote control, no credentials, no repository access, and no installation package.

## Record boundary

Duplicate `feedback-template.md` into `work/guided-review/` for each session. Completed reviewer records remain local in that ignored directory. Do not place names, employers, contact details, confidential information, or attributable quotations in checked-in documentation.
```

- [ ] **Step 5: Run the focused test and verify it passes**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py::test_guided_review_workspace_is_documented_and_local_only -v
```

Expected: PASS.

- [ ] **Step 6: Commit the workspace contract**

```bash
git add .gitignore clinical-protocol-poc/docs/guided-review/README.md clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py
git commit -m "docs: establish guided review workspace"
```

---

### Task 2: Presenter Guide and Preflight Checklist

**Files:**
- Create: `clinical-protocol-poc/docs/guided-review/presenter-guide.md`
- Create: `clinical-protocol-poc/docs/guided-review/preflight-checklist.md`
- Modify: `clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py`

**Interfaces:**
- Consumes: the two fixture paths and access boundary from Task 1.
- Produces: one repeatable 35-to-45-minute walkthrough and the required before-call verification sequence.

- [ ] **Step 1: Write the failing presenter-material test**

Append:

```python
def test_guided_review_presenter_materials_cover_both_workflows() -> None:
    review_root = Path(__file__).parents[3] / "docs" / "guided-review"
    guide = (review_root / "presenter-guide.md").read_text()
    preflight = (review_root / "preflight-checklist.md").read_text()
    combined = f"{guide}\n{preflight}"

    required = {
        "35 to 45 minutes",
        "Opening: 5 minutes",
        "Successful workflow: 10 to 15 minutes",
        "Mistake and recovery: 10 minutes",
        "Role-specific discussion: 10 to 15 minutes",
        "protocol.docx",
        "traceability.csv",
        "scorecard.html",
        "corrected-synopsis.docx",
        "Do not upload any document supplied by a reviewer",
        "Do not conceal unexpected behavior",
        "Do not record the call without explicit permission",
    }

    assert all(item in combined for item in required)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py::test_guided_review_presenter_materials_cover_both_workflows -v
```

Expected: FAIL because both presenter documents are absent.

- [ ] **Step 3: Write the presenter guide**

Create `docs/guided-review/presenter-guide.md` with these exact sections and instructions:

```markdown
# Presenter Guide

## Session contract

Allow 35 to 45 minutes. Share only the application window and retain control of every action. The reviewer may ask questions and request that any screen or artifact be revisited.

## Opening: 5 minutes

State: “This is a local synthetic proof of concept. It demonstrates evidence-controlled protocol drafting and mistake recovery. It is not validated and is not ready for clinical, regulatory, submission, operational, or production use.”

Explain that the walkthrough will show one successful study and one study that must be corrected before work can continue.

## Successful workflow: 10 to 15 minutes

Use `fixtures/reliability-pilot/standard/`.

1. Create and open a study.
2. Upload `synopsis.docx` and `template.docx`.
3. Process the synopsis.
4. Review each extracted fact and its source evidence.
5. Generate and review the four passages.
6. Create the export.
7. Download and briefly open `protocol.docx`, `traceability.csv`, and `scorecard.html`.
8. Point out the shared snapshot and the distinct purpose of each artifact.

## Mistake and recovery: 10 minutes

Use `fixtures/reliability-pilot/missing-dose/`.

1. Create a second study.
2. Upload `synopsis.docx` and `template.docx`.
3. Process the synopsis and show the missing-dose blocker.
4. Explain that the application does not invent the dose.
5. Upload `corrected-synopsis.docx` as an explicit replacement.
6. Show preserved version history.
7. Reprocess and continue after the blocker clears.

## Role-specific discussion: 10 to 15 minutes

Use `questions.md`. Ask the shared questions first, followed by the questions for the reviewer’s role. Record confusion before explaining it.

## Unexpected behavior

Do not conceal unexpected behavior. State what happened, record the action and visible result, and avoid improvising with unapproved files. If needed, continue by opening previously generated synthetic artifacts while retaining the failure in the feedback record.

## Closing

Thank the reviewer, explain that feedback will shape a broader synthetic Generalization and Evaluation milestone, and make no promise that a requested feature will be implemented.
```

- [ ] **Step 4: Write the preflight checklist**

Create `docs/guided-review/preflight-checklist.md`:

```markdown
# Guided Review Preflight Checklist

Complete every item before each call.

- [ ] Start the application with `make app` and confirm the health check succeeds.
- [ ] Confirm only synthetic demonstration data is visible.
- [ ] Confirm the standard study files are available.
- [ ] Confirm the missing-dose files and `corrected-synopsis.docx` are available.
- [ ] Complete the successful workflow once.
- [ ] Complete the mistake-and-recovery workflow once.
- [ ] Download and open `protocol.docx`, `traceability.csv`, and `scorecard.html`.
- [ ] Confirm screen sharing exposes only the application window.
- [ ] Close unrelated windows and disable distracting notifications.
- [ ] Prepare `questions.md` and a fresh local feedback record.
- [ ] Do not upload any document supplied by a reviewer.
- [ ] Do not conceal unexpected behavior.
- [ ] Do not record the call without explicit permission.
- [ ] Stop the application with `make down` after the session.
```

- [ ] **Step 5: Run the focused test and verify it passes**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py::test_guided_review_presenter_materials_cover_both_workflows -v
```

Expected: PASS.

- [ ] **Step 6: Commit presenter materials**

```bash
git add clinical-protocol-poc/docs/guided-review/presenter-guide.md clinical-protocol-poc/docs/guided-review/preflight-checklist.md clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py
git commit -m "docs: add guided review walkthrough"
```

---

### Task 3: Questions and Private Feedback Record

**Files:**
- Create: `clinical-protocol-poc/docs/guided-review/questions.md`
- Create: `clinical-protocol-poc/docs/guided-review/feedback-template.md`
- Modify: `clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py`

**Interfaces:**
- Consumes: reviewer sequence and discussion window from the approved design.
- Produces: one shared question set, three role-specific question sets, and a consistent private record schema.

- [ ] **Step 1: Write the failing question-and-record test**

Append:

```python
def test_guided_review_questions_and_feedback_schema_are_complete() -> None:
    review_root = Path(__file__).parents[3] / "docs" / "guided-review"
    questions = (review_root / "questions.md").read_text()
    feedback = (review_root / "feedback-template.md").read_text()

    assert all(
        heading in questions
        for heading in (
            "## Shared questions",
            "## R&D reviewer with limited protocol experience",
            "## CRO reviewer",
            "## Medical writer",
        )
    )
    assert all(
        field in feedback
        for field in (
            "Reviewer role and relevant experience",
            "Direct observations",
            "Points of confusion",
            "Trust or safety concerns",
            "Workflow mismatches",
            "Document or vocabulary variations described",
            "Commercial or pilot interest",
            "Presenter interpretation",
            "Items requiring confirmation",
        )
    )
    assert "Do not record names, employers, or contact details" in feedback
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py::test_guided_review_questions_and_feedback_schema_are_complete -v
```

Expected: FAIL because the question and feedback files are absent.

- [ ] **Step 3: Create the question set**

Create `docs/guided-review/questions.md` with this complete content:

```markdown
# Guided Review Questions

Ask questions neutrally. Record confusion and criticism before explaining or defending the application. Ask the shared questions first, then the questions for the reviewer’s role.

## Shared questions

- What did you think the application was doing?
- Which part seemed most valuable?
- Which part was confusing or unnecessary?
- What would make you distrust the result?
- What mistakes would you expect the application to catch?
- Where would this fit, or fail to fit, in your current workflow?
- What would you need to see before recommending a controlled pilot?

## R&D reviewer with limited protocol experience

- Was the guidance understandable without specialized protocol experience?
- Did the application explain why each decision was required?
- Could someone accidentally approve information they did not understand?
- Which terms, screens, or actions required more explanation?

## CRO reviewer

- Where could this reduce handoffs, duplication, or review cycles?
- Are correction, versioning, archive, and export workflows realistic?
- Which sponsor templates and document variations are common?
- Which security, audit, integration, approval, or procurement requirements would block adoption?

## Medical writer

- Were the extracted facts and their evidence accurate and usable?
- Were draft passages appropriately constrained by approved facts?
- Was passage review practical for real authoring work?
- Which sections, templates, consistency checks, and Microsoft Word capabilities are essential?
- Would the traceability output reduce work or create additional work?
```

- [ ] **Step 4: Create the private feedback template**

Create `docs/guided-review/feedback-template.md`:

```markdown
# Guided Review Feedback Record

Store the completed copy under `work/guided-review/`. Completed records remain local and are not committed.

Do not record names, employers, or contact details. Do not include confidential information or attributable quotations without permission.

## Session

- Reviewer role and relevant experience:
- Session date and duration:
- Workflows demonstrated:
- Demonstration failures or deviations: None observed / Describe factually

## Evidence

### Direct observations

Record visible behavior and reviewer statements without interpretation.

### Points of confusion

Record what was unclear before providing additional explanation.

### Perceived value

Record the workflow, output, or control the reviewer considered useful.

### Trust or safety concerns

Record conditions that would reduce confidence or prevent use.

### Workflow mismatches

Record differences from the reviewer’s current process.

### Requested capabilities

Record requests without promising implementation.

### Document or vocabulary variations described

Record only nonconfidential characteristics; do not collect source documents.

### Commercial or pilot interest

Record the evidence and conditions stated by the reviewer.

## Interpretation

### Presenter interpretation

Separate inference from direct evidence.

### Items requiring confirmation

List points another reviewer should confirm or challenge.

## Classification

Mark every applicable category:

- [ ] Usability problem
- [ ] Clinical-content or writing risk
- [ ] Workflow mismatch
- [ ] Missing document variation
- [ ] Missing evaluation case
- [ ] Security or compliance requirement
- [ ] Commercial opportunity
- [ ] Future feature request
```

- [ ] **Step 5: Run the focused test and verify it passes**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py::test_guided_review_questions_and_feedback_schema_are_complete -v
```

Expected: PASS.

- [ ] **Step 6: Commit questions and record template**

```bash
git add clinical-protocol-poc/docs/guided-review/questions.md clinical-protocol-poc/docs/guided-review/feedback-template.md clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py
git commit -m "docs: add guided review feedback tools"
```

---

### Task 4: Evidence Synthesis and Roadmap Decisions

**Files:**
- Create: `clinical-protocol-poc/docs/guided-review/synthesis-template.md`
- Modify: `clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py`

**Interfaces:**
- Consumes: three completed local feedback records from Task 3 after the sessions occur.
- Produces: a sanitized cross-review comparison and exact routing into Generalization and Evaluation, M11/protocol expansion, security/deployment, or no action.

- [ ] **Step 1: Write the failing synthesis-contract test**

Append:

```python
def test_guided_review_synthesis_preserves_evidence_and_roadmap_boundaries() -> None:
    path = (
        Path(__file__).parents[3]
        / "docs"
        / "guided-review"
        / "synthesis-template.md"
    )
    synthesis = path.read_text()
    required = {
        "R&D reviewer",
        "CRO reviewer",
        "Medical writer",
        "Repeated findings",
        "Role-specific differences",
        "Serious safety or content-integrity concerns",
        "Generalization and Evaluation",
        "M11 and protocol expansion",
        "Security and deployment",
        "No action until additional evidence exists",
        "Do not include reviewer names, employers, contact details",
    }

    assert all(item in synthesis for item in required)
    assert "Every actionable finding receives one primary destination" in synthesis
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py::test_guided_review_synthesis_preserves_evidence_and_roadmap_boundaries -v
```

Expected: FAIL because `synthesis-template.md` is absent.

- [ ] **Step 3: Create the synthesis template**

Create `docs/guided-review/synthesis-template.md`:

```markdown
# Guided External Review Synthesis

Use this template only after the R&D reviewer, CRO reviewer, and Medical writer sessions are complete.

Do not include reviewer names, employers, contact details, confidential information, or attributable quotations. Summarize evidence by role.

## Reviews completed

| Reviewer role | Core workflows shown | Feedback record complete | Demonstration failure recorded |
| --- | --- | --- | --- |
| R&D reviewer | Yes / No | Yes / No | None / Summarized below |
| CRO reviewer | Yes / No | Yes / No | None / Summarized below |
| Medical writer | Yes / No | Yes / No | None / Summarized below |

## Repeated findings

For each finding, list the roles that raised it and the direct evidence supporting it.

## Role-specific differences

Preserve conflicting or specialized feedback by reviewer role. Do not average disagreements into a false consensus.

## Serious safety or content-integrity concerns

List every serious concern even if only one reviewer identified it.

## Demonstration failures

Summarize the action, visible result, and effect on the review. Do not conceal failures or relabel them as reviewer confusion.

## Actionable findings

Every actionable finding receives one primary destination.

| Finding | Evidence | Classification | Primary destination | Decision and reason |
| --- | --- | --- | --- | --- |

Allowed primary destinations:

1. Generalization and Evaluation
2. M11 and protocol expansion
3. Security and deployment
4. No action until additional evidence exists

## Generalization and Evaluation inputs

List the document variations, vocabulary variations, failure modes, metrics, and acceptance criteria supported by review evidence or an existing documented limitation.

## Deferred roadmap findings

List M11/protocol-expansion and security/deployment findings without turning them into current commitments.

## Conclusion

State whether the evidence is specific enough to design Generalization and Evaluation. Do not make a clinical, regulatory, submission, operational, production, validation, or readiness claim.
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py::test_guided_review_synthesis_preserves_evidence_and_roadmap_boundaries -v
```

Expected: PASS.

- [ ] **Step 5: Commit the synthesis method**

```bash
git add clinical-protocol-poc/docs/guided-review/synthesis-template.md clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py
git commit -m "docs: define guided review synthesis"
```

---

### Task 5: Discoverability, Full Verification, and Synthetic Dry Run

**Files:**
- Modify: `clinical-protocol-poc/README.md`
- Modify: `clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py`

**Interfaces:**
- Consumes: the complete guided-review kit from Tasks 1 through 4 and the existing self-service application.
- Produces: a discoverable, fully verified kit and evidence that both approved workflows remain demonstrable before external scheduling begins.

- [ ] **Step 1: Write the failing discoverability test**

Append:

```python
def test_project_readme_links_the_guided_review_kit() -> None:
    readme = (Path(__file__).parents[3] / "README.md").read_text()

    assert "docs/guided-review/README.md" in readme
    assert "presenter-controlled synthetic external review" in readme
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py::test_project_readme_links_the_guided_review_kit -v
```

Expected: FAIL because the project README does not yet link the kit.

- [ ] **Step 3: Add the review-kit entrypoint to the README**

Add this paragraph under `## Demo entrypoint`:

```markdown
For a presenter-controlled synthetic external review, use `docs/guided-review/README.md`. It contains the approved walkthrough, preflight checks, role-specific questions, private feedback template, and synthesis method. Reviewers watch through screen sharing while the presenter retains control of the local application.
```

- [ ] **Step 4: Run documentation controls**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py -v
```

Expected: all documentation-control tests PASS.

- [ ] **Step 5: Run static checks and the full automated suite**

Run from `clinical-protocol-poc/`:

```bash
make lint
make typecheck
make test
make evaluation
```

Expected: all commands exit zero, all 13 adversarial export-denial scenarios pass, and evaluation prints `unsupported clinical facts exported: 0`.

- [ ] **Step 6: Run the two-stack fixture verification**

Run:

```bash
make reliability-pilot
```

Expected: both clean-stack runs pass 6 of 6 studies, all three expected pre-correction denials occur, repeatability passes with no mismatches, and unsupported clinical facts exported remains zero.

- [ ] **Step 7: Perform the presenter-controlled dry run**

Run:

```bash
make app
```

Open `http://127.0.0.1:3000` and follow `docs/guided-review/presenter-guide.md` with the standard and missing-dose fixture packs. Complete every item in `docs/guided-review/preflight-checklist.md` except screen sharing and reviewer-specific discussion.

Expected:

- the standard study reaches export and all three artifacts open;
- the missing-dose study stops for missing dose information;
- explicit upload of `corrected-synopsis.docx` preserves source history;
- reprocessing clears the source blocker and permits the workflow to continue; and
- no real or reviewer-supplied document is used.

Stop the application:

```bash
make down
```

- [ ] **Step 8: Check documentation hygiene**

Run:

```bash
rg -n "TB[D]|TO[D]O|FIXM[E]" docs/guided-review README.md
rg -ni "clinical readiness|regulatory readiness|submission readiness|operational readiness|production readiness|readiness percentage" docs/guided-review
git diff --check
git status --short
```

Expected: no incomplete markers, no positive readiness claims, no whitespace errors, and only the intended README and test changes remain uncommitted.

- [ ] **Step 9: Commit the verified entrypoint**

```bash
git add clinical-protocol-poc/README.md clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py
git commit -m "docs: publish verified guided review kit"
```

---

## Operational Handoff After Implementation

These are human review checkpoints, not software implementation tasks:

1. Duplicate `docs/guided-review/feedback-template.md` into ignored `work/guided-review/` before each call.
2. Conduct the R&D review and complete its local record.
3. Conduct the CRO review and complete its local record.
4. Conduct the medical-writer review and complete its local record.
5. Use `docs/guided-review/synthesis-template.md` to prepare a sanitized synthesis after all three sessions.
6. Review the synthesis together before designing the Generalization and Evaluation milestone.

No reviewer record is committed, pushed, emailed, or otherwise shared by the implementation workflow.
