# Clinical-Trial Protocol POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, demonstrable POC that converts a synthetic study synopsis and Word template into writer-reviewed protocol sections, a deterministic Word document, a traceability report, and a non-composite quality scorecard while preventing unsupported clinical content from approval or export.

**Architecture:** Build a modular monolith: a Python/FastAPI backend with domain modules, PostgreSQL persistence, local S3-compatible file storage, a versioned SQLite FTS guidance index for the POC, and a React/Next.js frontend. All drafting flows through a controlled AI gateway, but deterministic claim/fact validators and an immutable export-snapshot gate are authoritative. Implement in five vertical increments so every increment ends in working, testable software.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL 16, MinIO, python-docx, defusedxml, Next.js 15, React 19, TypeScript, Tailwind, pytest, Hypothesis, Vitest, Testing Library, Playwright, Docker Compose.

---

## 1. Scope, decisions, and delivery increments

This plan implements the approved design specification at `outputs/clinical-trial-protocol-poc-design-specification.md`. It deliberately uses a bounded synthetic study, one template family, one writer role, and a pluggable AI provider. The first working path uses a deterministic fixture provider so safety tests never depend on network access or nondeterministic model behavior.

The five increments are:

1. **Foundation and ingest:** runnable stack, tenant-scoped persistence, files, audit events, safe DOCX ingest.
2. **Facts and review:** source evidence, candidate extraction, explicit critical-fact approval, canonical study model, conflicts, impact links.
3. **Governed drafting:** approved guidance releases, controlled gateway, claim mapping, deterministic validation, writer passage lifecycle.
4. **Export:** scorecard, immutable snapshot, deterministic DOCX rendering, traceability report, server-side hard gate.
5. **Evaluation:** Guided Review UI, Model Explorer, authoring UI, adversarial gold-standard suite, operational documentation.

Implementation must not broaden scope into full protocol generation, production authentication, electronic signatures, regulated-system validation, or submission-readiness claims.

## 2. Repository map

Create this structure before feature work:

```text
clinical-protocol-poc/
├── README.md                         # Local setup, safety statement, demo flow
├── Makefile                          # Reproducible developer commands
├── compose.yaml                      # API, web, Postgres, MinIO
├── .env.example                      # Non-secret configuration contract
├── docs/
│   ├── architecture.md               # Module boundaries and data flow
│   ├── safety-case.md                # Invariant-to-control mapping
│   └── demo-script.md                # Bounded POC walkthrough
├── fixtures/
│   ├── synthetic-study/              # Synopsis, template, gold facts, expected findings
│   └── guidance/                     # Versioned approved guidance fixtures
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/                   # Database revisions
│   ├── src/protocol_poc/
│   │   ├── app.py                    # FastAPI composition root
│   │   ├── config.py                 # Typed configuration
│   │   ├── db.py                     # Sessions and transaction boundary
│   │   ├── tenancy.py                # Tenant context enforcement
│   │   ├── common/                   # IDs, time, errors, result types
│   │   ├── audit/                    # Append-only event recording/query
│   │   ├── files/                    # Object storage and checksums
│   │   ├── ingest/                   # Safe DOCX parse and evidence locations
│   │   ├── studies/                  # Study, evidence, fact, relationship model
│   │   ├── review/                   # Fact review, conflicts, impact/invalidation
│   │   ├── guidance/                 # Releases, FTS index, governed retrieval
│   │   ├── ai_gateway/               # Task policy, schemas, provider adapters
│   │   ├── drafting/                 # Passages, claims, support maps, lifecycle
│   │   ├── validation/               # Deterministic and semantic findings
│   │   ├── quality/                  # Scorecard dimensions and blockers
│   │   ├── export/                   # Snapshot, hard gate, orchestration
│   │   └── rendering/                # DOCX and traceability generation
│   └── tests/
│       ├── unit/                     # Pure domain tests
│       ├── integration/              # DB/storage/API tests
│       ├── contract/                 # AI schemas and provider contracts
│       └── evaluation/               # Gold-standard/adversarial tests
└── frontend/
    ├── package.json
    ├── next.config.ts
    ├── src/app/                      # Routes and layouts
    ├── src/features/                 # Guided review, explorer, drafting, quality
    ├── src/lib/                      # API client and shared types
    └── tests/                        # Vitest and Playwright tests
```

Boundaries are enforced as follows: route modules call application services; services own transactions; domain validators are pure functions; only repositories access SQLAlchemy; only the file module accesses object storage; only the AI gateway calls a model provider; only export orchestration can create export snapshots and artifacts.

## 3. Definition of done for every task

- New behavior starts with a failing test and follows red → green → refactor.
- Tenant identity is required on every persisted aggregate and every query.
- Material state changes append an audit event in the same database transaction.
- API errors use stable problem codes and do not leak clinical content into logs.
- Formatting, typing, unit tests, and affected integration tests pass.
- No task may weaken the export gate or add a bypass/waiver for hard blockers.
- Commit only the files listed in the task; do not commit secrets or generated artifacts.

## 4. Implementation tasks

### Task 1: Bootstrap a reproducible local stack

**Files:**
- Create: `clinical-protocol-poc/README.md`
- Create: `clinical-protocol-poc/.env.example`
- Create: `clinical-protocol-poc/Makefile`
- Create: `clinical-protocol-poc/compose.yaml`
- Create: `clinical-protocol-poc/backend/pyproject.toml`
- Create: `clinical-protocol-poc/backend/src/protocol_poc/app.py`
- Create: `clinical-protocol-poc/backend/src/protocol_poc/config.py`
- Create: `clinical-protocol-poc/backend/tests/unit/test_health.py`
- Create: `clinical-protocol-poc/frontend/package.json`
- Create: `clinical-protocol-poc/frontend/src/app/page.tsx`

- [ ] **Step 1: Write the failing API smoke test**

```python
from fastapi.testclient import TestClient

from protocol_poc.app import create_app


def test_health_reports_ready() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "protocol-poc"}
```

- [ ] **Step 2: Run the smoke test and confirm the expected failure**

Run: `cd clinical-protocol-poc/backend && uv sync --all-groups && uv run pytest tests/unit/test_health.py -v`  
Expected: FAIL because `protocol_poc.app` does not exist.

- [ ] **Step 3: Add the minimal FastAPI composition root**

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Clinical Protocol POC", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ready", "service": "protocol-poc"}

    return app


app = create_app()
```

Declare pinned runtime/dev dependencies in `pyproject.toml`; add `make bootstrap`, `make test`, `make lint`, `make up`, and `make down`; configure Compose health checks for Postgres, MinIO, API, and web; keep all credentials as local-only defaults in `.env.example`.

- [ ] **Step 4: Add the frontend smoke page and test the stack**

The page must show “Clinical Protocol POC”, “Synthetic data only”, and “No protocol is claimed clinically or regulatorily ready.” Run: `make test && docker compose up --build -d && curl --fail http://localhost:8000/health`  
Expected: all tests PASS and the health request returns HTTP 200.

- [ ] **Step 5: Commit**

```bash
git add clinical-protocol-poc
git commit -m "chore: bootstrap protocol POC stack"
```

### Task 2: Add tenant-scoped persistence and append-only audit events

**Files:**
- Create: `backend/src/protocol_poc/common/ids.py`
- Create: `backend/src/protocol_poc/db.py`
- Create: `backend/src/protocol_poc/tenancy.py`
- Create: `backend/src/protocol_poc/audit/models.py`
- Create: `backend/src/protocol_poc/audit/service.py`
- Create: `backend/migrations/versions/0001_tenant_audit.py`
- Test: `backend/tests/integration/test_audit_append_only.py`

- [ ] **Step 1: Write failing tests for isolation and immutability**

```python
def test_events_are_scoped_to_tenant(audit_service, tenant_a, tenant_b):
    audit_service.append(tenant_a, "study.created", "study", "s1", {"version": 1})
    assert len(audit_service.list_for(tenant_a, "study", "s1")) == 1
    assert audit_service.list_for(tenant_b, "study", "s1") == []


def test_audit_event_cannot_be_updated(db_session, saved_event):
    saved_event.event_type = "changed"
    with pytest.raises(AppendOnlyViolation):
        db_session.commit()
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/integration/test_audit_append_only.py -v`  
Expected: FAIL because the audit model and service do not exist.

- [ ] **Step 3: Implement tenant context, ULID identifiers, and audit service**

`AuditEvent` fields: `id`, `tenant_id`, `event_type`, `aggregate_type`, `aggregate_id`, `payload_json`, `actor_type`, `actor_id`, `occurred_at`. Block ORM update/delete operations for this table and deny queries without an explicit `TenantContext`.

```python
@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    actor_id: str


class AuditService:
    def append(self, ctx: TenantContext, event_type: str, aggregate_type: str,
               aggregate_id: str, payload: dict[str, object]) -> AuditEvent:
        event = AuditEvent.new(ctx, event_type, aggregate_type, aggregate_id, payload)
        self.session.add(event)
        return event
```

- [ ] **Step 4: Verify migration and isolation**

Run: `uv run alembic upgrade head && uv run pytest tests/integration/test_audit_append_only.py -v`  
Expected: PASS; attempts to mutate or cross-read audit events fail.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc backend/migrations backend/tests
git commit -m "feat: add tenant-scoped append-only audit trail"
```

### Task 3: Store and safely ingest DOCX inputs

**Files:**
- Create: `backend/src/protocol_poc/files/models.py`
- Create: `backend/src/protocol_poc/files/service.py`
- Create: `backend/src/protocol_poc/ingest/docx_parser.py`
- Create: `backend/src/protocol_poc/ingest/service.py`
- Create: `backend/src/protocol_poc/ingest/routes.py`
- Create: `backend/migrations/versions/0002_files_evidence.py`
- Test: `backend/tests/unit/ingest/test_docx_parser.py`
- Test: `backend/tests/integration/ingest/test_upload.py`

- [ ] **Step 1: Write failing parser tests**

```python
def test_parser_preserves_paragraph_and_table_locations(synthetic_synopsis_docx):
    evidence = DocxParser().parse(synthetic_synopsis_docx)
    assert evidence[0].location.kind == "paragraph"
    assert evidence[0].location.index == 0
    assert any(item.location.kind == "table_cell" for item in evidence)


def test_parser_rejects_external_relationships(docx_with_external_link):
    with pytest.raises(UnsafeDocumentError, match="external relationship"):
        DocxParser().parse(docx_with_external_link)
```

- [ ] **Step 2: Run the parser tests**

Run: `uv run pytest tests/unit/ingest/test_docx_parser.py -v`  
Expected: FAIL because `DocxParser` is undefined.

- [ ] **Step 3: Implement bounded ingestion**

Allow `.docx` only; enforce configured byte/uncompressed-size/entry-count limits; verify the ZIP signature; reject macros, external relationships, path traversal, and encrypted files; parse XML with `defusedxml`; calculate SHA-256; preserve paragraph/table coordinates and normalized text. Store `FileRecord`, `FileVersion`, `SourceEvidence`, and `IngestJob` rows and append success/failure audit events.

- [ ] **Step 4: Add upload API and verify idempotency**

`POST /api/studies/{study_id}/inputs` accepts `role=synopsis|template`. Re-uploading identical bytes returns the existing file version; different bytes create a new version. Run: `uv run pytest tests/unit/ingest tests/integration/ingest -v`  
Expected: PASS, including hostile DOCX cases.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/files backend/src/protocol_poc/ingest backend/migrations backend/tests
git commit -m "feat: safely ingest versioned protocol inputs"
```

### Task 4: Define the canonical study and fact model

**Files:**
- Create: `backend/src/protocol_poc/studies/enums.py`
- Create: `backend/src/protocol_poc/studies/models.py`
- Create: `backend/src/protocol_poc/studies/schemas.py`
- Create: `backend/src/protocol_poc/studies/repository.py`
- Create: `backend/migrations/versions/0003_study_model.py`
- Test: `backend/tests/unit/studies/test_fact_rules.py`
- Test: `backend/tests/integration/studies/test_relationships.py`

- [ ] **Step 1: Write failing domain tests**

```python
def test_dose_requires_value_and_ucum_unit():
    with pytest.raises(ValidationError):
        FactValue(kind="dose", value="10", unit=None)


def test_endpoint_requires_objective_and_timepoint_links():
    endpoint = Endpoint(name="HbA1c change", hierarchy="primary")
    findings = validate_endpoint_relationships(endpoint)
    assert {f.code for f in findings} == {
        "ENDPOINT_OBJECTIVE_MISSING", "ENDPOINT_TIMEPOINT_MISSING"
    }
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/unit/studies tests/integration/studies -v`  
Expected: FAIL because the study domain is undefined.

- [ ] **Step 3: Implement entities and typed fact values**

Create tenant-scoped/versioned records for `Study`, `Fact`, `FactVersion`, `Objective`, `Endpoint`, `Timepoint`, `Population`, `Arm`, `Intervention`, `EligibilityCriterion`, `ScheduleConcept`, and typed links. `FactStatus` is exactly `candidate|approved|rejected|superseded|conflicted`. `FactValue` supports string, integer, decimal, coded value, duration, dose, and structured criterion; numeric clinical values require units where applicable.

- [ ] **Step 4: Add database constraints and relationship tests**

Enforce no dangling links, one current fact version, and tenant-matched foreign keys. Run: `uv run alembic upgrade head && uv run pytest tests/unit/studies tests/integration/studies -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/studies backend/migrations backend/tests
git commit -m "feat: add canonical study and fact model"
```

### Task 5: Extract candidates through a schema-constrained fixture gateway

**Files:**
- Create: `backend/src/protocol_poc/ai_gateway/tasks.py`
- Create: `backend/src/protocol_poc/ai_gateway/schemas.py`
- Create: `backend/src/protocol_poc/ai_gateway/provider.py`
- Create: `backend/src/protocol_poc/ai_gateway/fixture_provider.py`
- Create: `backend/src/protocol_poc/ai_gateway/service.py`
- Create: `backend/src/protocol_poc/studies/extraction_service.py`
- Test: `backend/tests/contract/ai_gateway/test_extraction_contract.py`
- Test: `backend/tests/integration/studies/test_extraction.py`

- [ ] **Step 1: Write failing gateway contract tests**

```python
def test_extraction_rejects_missing_source_location(gateway):
    gateway.provider.response = {"candidates": [{"kind": "dose", "value": "10 mg"}]}
    with pytest.raises(GatewaySchemaError):
        gateway.run(TaskType.EXTRACT_FACTS, ExtractionInput(evidence_ids=["e1"]))


def test_extracted_candidate_is_never_approved(extraction_service, evidence):
    facts = extraction_service.extract(evidence)
    assert all(f.status is FactStatus.CANDIDATE for f in facts)
```

- [ ] **Step 2: Run contract tests**

Run: `uv run pytest tests/contract/ai_gateway tests/integration/studies/test_extraction.py -v`  
Expected: FAIL because the gateway contracts do not exist.

- [ ] **Step 3: Implement allowlisted gateway tasks**

Define task types `extract_facts`, `retrieve_guidance`, `draft_passage`, `map_claims`, `semantic_review`, and `explain_finding`. Each has distinct Pydantic input/output schemas. The fixture provider reads deterministic JSON by scenario. The gateway records task type, model/provider identifier, prompt version, evidence/fact IDs, response hash, schema result, and status; raw uploaded instructions never enter the system instruction field.

- [ ] **Step 4: Implement extraction persistence and verify fail-closed behavior**

Malformed output creates a failed gateway call and no facts. Valid output creates candidate facts linked to exact evidence IDs/locations. Run: `uv run pytest tests/contract/ai_gateway tests/integration/studies/test_extraction.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/ai_gateway backend/src/protocol_poc/studies backend/tests
git commit -m "feat: add constrained candidate extraction gateway"
```

### Task 6: Implement Guided Review fact approval and conflict handling

**Files:**
- Create: `backend/src/protocol_poc/review/fact_service.py`
- Create: `backend/src/protocol_poc/review/conflicts.py`
- Create: `backend/src/protocol_poc/review/routes.py`
- Create: `backend/migrations/versions/0004_fact_review.py`
- Test: `backend/tests/unit/review/test_fact_review.py`
- Test: `backend/tests/integration/review/test_fact_review_api.py`

- [ ] **Step 1: Write failing approval tests**

```python
def test_critical_fact_requires_explicit_confirmation(service, critical_candidate, writer):
    with pytest.raises(ExplicitConfirmationRequired):
        service.approve(critical_candidate.id, writer, explicitly_confirmed=False)


def test_conflicting_candidate_cannot_be_approved(service, conflicted_candidate, writer):
    with pytest.raises(UnresolvedConflict):
        service.approve(conflicted_candidate.id, writer, explicitly_confirmed=True)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/review tests/integration/review -v`  
Expected: FAIL because review services are undefined.

- [ ] **Step 3: Implement review commands**

Add `approve`, `correct_and_approve`, `reject`, `defer`, and `resolve_conflict`. Every command checks version preconditions, requires writer identity, appends an audit event, and returns the resulting current fact. Editing an approved fact creates a superseding version; it never changes the approved row in place.

- [ ] **Step 4: Add queue API and verify criticality ordering**

`GET /api/studies/{id}/fact-review` returns blockers first, then critical unresolved facts, conflicts, ambiguities, and low-confidence candidates. Run: `uv run pytest tests/unit/review tests/integration/review -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/review backend/migrations backend/tests
git commit -m "feat: add explicit fact review workflow"
```

### Task 7: Govern approved guidance releases and closed-world retrieval

**Files:**
- Create: `backend/src/protocol_poc/guidance/models.py`
- Create: `backend/src/protocol_poc/guidance/index.py`
- Create: `backend/src/protocol_poc/guidance/service.py`
- Create: `backend/src/protocol_poc/guidance/routes.py`
- Create: `backend/migrations/versions/0005_guidance.py`
- Test: `backend/tests/unit/guidance/test_index.py`
- Test: `backend/tests/integration/guidance/test_retrieval.py`

- [ ] **Step 1: Write failing retrieval tests**

```python
def test_retrieval_returns_only_approved_active_release(service, draft_release, active_release):
    results = service.search("eligibility", tenant_id=active_release.tenant_id)
    assert results
    assert {r.release_id for r in results} == {active_release.id}


def test_sponsor_pattern_cannot_cross_tenant(service, sponsor_pattern, other_tenant):
    assert service.search("randomized", tenant_id=other_tenant) == []
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/guidance tests/integration/guidance -v`  
Expected: FAIL because guidance governance is undefined.

- [ ] **Step 3: Implement release state and derived FTS index**

Model `GuidanceSource`, `GuidanceRelease`, `GuidanceChunk`, and `ReusablePattern`. Release states are `draft|approved|active|retired`. Index only active, approved chunks; store source, version, section/location, applicability tags, content hash, tenant visibility, and release ID. Rebuild indexes from authoritative relational records.

- [ ] **Step 4: Verify irrelevant and retired guidance exclusion**

Run: `uv run pytest tests/unit/guidance tests/integration/guidance -v`  
Expected: PASS; irrelevant, draft, retired, and cross-tenant content is excluded.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/guidance backend/migrations backend/tests
git commit -m "feat: add governed guidance releases and retrieval"
```

### Task 8: Draft passages only from approved context

**Files:**
- Create: `backend/src/protocol_poc/drafting/models.py`
- Create: `backend/src/protocol_poc/drafting/context.py`
- Create: `backend/src/protocol_poc/drafting/service.py`
- Create: `backend/src/protocol_poc/drafting/routes.py`
- Create: `backend/migrations/versions/0006_passages.py`
- Test: `backend/tests/unit/drafting/test_context.py`
- Test: `backend/tests/integration/drafting/test_generate_passage.py`

- [ ] **Step 1: Write failing closed-world context tests**

```python
def test_context_contains_only_approved_current_facts(builder, approved_fact, candidate_fact):
    context = builder.for_section("objectives_endpoints")
    assert approved_fact.id in context.fact_ids
    assert candidate_fact.id not in context.fact_ids


def test_missing_required_fact_becomes_placeholder_not_guess(service, study_without_dose):
    result = service.generate(study_without_dose.id, section="study_design")
    assert "[[REQUIRED: intervention dose]]" in result.text
    assert result.status == "blocked"
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/drafting tests/integration/drafting -v`  
Expected: FAIL because drafting context and passage lifecycle do not exist.

- [ ] **Step 3: Implement passage-level generation**

Create `Passage`, `PassageVersion`, `Claim`, and `SupportLink`. `DraftContextBuilder` loads only current approved facts and active approved guidance for the requested scoped section. The output schema requires passage text, explicit placeholders, claims, fact IDs, and guidance IDs. Reject any returned ID absent from the supplied context.

- [ ] **Step 4: Verify all four scoped section types**

Run fixture scenarios for `synopsis`, `objectives_endpoints`, `study_design`, and `eligibility`. Run: `uv run pytest tests/unit/drafting tests/integration/drafting -v`  
Expected: PASS; no candidate fact or unsupported suggestion enters context.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/drafting backend/migrations backend/tests
git commit -m "feat: draft passages from approved context only"
```

### Task 9: Add deterministic claim and cross-model validation

**Files:**
- Create: `backend/src/protocol_poc/validation/findings.py`
- Create: `backend/src/protocol_poc/validation/claims.py`
- Create: `backend/src/protocol_poc/validation/clinical_values.py`
- Create: `backend/src/protocol_poc/validation/relationships.py`
- Create: `backend/src/protocol_poc/validation/service.py`
- Test: `backend/tests/unit/validation/test_clinical_values.py`
- Test: `backend/tests/unit/validation/test_relationships.py`
- Test: `backend/tests/integration/validation/test_passage_validation.py`

- [ ] **Step 1: Write failing safety tests**

```python
@pytest.mark.parametrize("text,code", [
    ("Participants receive 20 mg daily.", "UNSUPPORTED_DOSE"),
    ("The primary endpoint is assessed at Week 24.", "TIMEPOINT_MISMATCH"),
    ("Adults aged 18 to 75 years are eligible.", "UNSUPPORTED_ELIGIBILITY"),
])
def test_unsupported_clinical_values_are_blockers(validator, approved_model, text, code):
    findings = validator.validate_text(text, approved_model)
    assert any(f.code == code and f.severity == "blocker" for f in findings)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/validation tests/integration/validation -v`  
Expected: FAIL because validators are undefined.

- [ ] **Step 3: Implement normalized deterministic comparison**

Normalize decimal forms, UCUM-compatible units, durations, ranges, endpoint labels, arm/intervention links, populations, criterion identifiers, and timepoints. A claim is supported only when all clinical values and relationships match current approved facts. Unknown parsing, ambiguous claim boundaries, missing support links, and validator exceptions produce blockers rather than passes.

- [ ] **Step 4: Add semantic-review isolation**

Semantic review may add findings but cannot change, dismiss, or downgrade deterministic findings. Run: `uv run pytest tests/unit/validation tests/integration/validation -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/validation backend/tests
git commit -m "feat: add fail-closed clinical content validation"
```

### Task 10: Implement writer passage review and fact-change invalidation

**Files:**
- Create: `backend/src/protocol_poc/drafting/review_service.py`
- Create: `backend/src/protocol_poc/review/impact_service.py`
- Modify: `backend/src/protocol_poc/review/fact_service.py`
- Test: `backend/tests/unit/drafting/test_passage_review.py`
- Test: `backend/tests/integration/review/test_invalidation.py`

- [ ] **Step 1: Write failing acceptance/invalidation tests**

```python
def test_passage_with_blocker_cannot_be_accepted(service, blocked_passage, writer):
    with pytest.raises(PassageBlocked):
        service.accept(blocked_passage.id, writer)


def test_fact_edit_invalidates_dependent_accepted_passage(fact_service, accepted_passage, dose_fact):
    fact_service.correct_and_approve(dose_fact.id, {"value": "20", "unit": "mg"})
    assert accepted_passage.reload().status == "stale"
    assert accepted_passage.reload().invalidation_reason == "supporting_fact_changed"
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/drafting/test_passage_review.py tests/integration/review/test_invalidation.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implement review lifecycle**

Passage statuses are `draft|blocked|ready_for_review|accepted|rejected|stale`. Implement `accept`, `edit`, `reject`, and `regenerate`. Writer edits create a new passage version and rerun claim mapping plus deterministic validation. `ImpactService` traverses support links and marks dependent accepted passages stale in the same transaction as fact supersession.

- [ ] **Step 4: Verify stale content cannot be accepted/exported**

Run: `uv run pytest tests/unit/drafting tests/integration/review -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/drafting backend/src/protocol_poc/review backend/tests
git commit -m "feat: add passage review and dependency invalidation"
```

### Task 11: Calculate the non-composite quality scorecard

**Files:**
- Create: `backend/src/protocol_poc/quality/models.py`
- Create: `backend/src/protocol_poc/quality/service.py`
- Create: `backend/src/protocol_poc/quality/routes.py`
- Test: `backend/tests/unit/quality/test_scorecard.py`

- [ ] **Step 1: Write failing scorecard tests**

```python
def test_scorecard_has_dimensions_and_no_composite(service, blocked_study):
    card = service.calculate(blocked_study.id)
    assert set(card.dimensions) == {
        "completeness", "consistency", "traceability", "template_conformance",
        "writer_review_status", "approved_guidance_coverage"
    }
    assert not hasattr(card, "overall_score")
    assert card.export_status == "blocked"


def test_required_placeholder_is_hard_blocker(service, study_with_placeholder):
    card = service.calculate(study_with_placeholder.id)
    assert "REQUIRED_PLACEHOLDER" in {b.code for b in card.blockers}
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/quality/test_scorecard.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implement transparent dimension results**

Each dimension returns `status`, `passed_count`, `applicable_count`, and linked findings. Allowed status labels are `pass|needs_review|blocked|not_applicable`. Do not calculate or expose an overall numeric score. Hard blockers include unsupported content, unresolved critical facts, critical contradictions, incomplete provenance, required placeholders, stale passages, and incomplete/failed mandatory validation.

- [ ] **Step 4: Verify wording and API schema**

Assert the response contains no `ready`, `regulatorily ready`, `clinically ready`, or `submission ready` claim except the explicit disclaimer. Run: `uv run pytest tests/unit/quality -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/quality backend/tests
git commit -m "feat: add non-composite protocol quality scorecard"
```

### Task 12: Create immutable export snapshots and a server-side hard gate

**Files:**
- Create: `backend/src/protocol_poc/export/models.py`
- Create: `backend/src/protocol_poc/export/gate.py`
- Create: `backend/src/protocol_poc/export/service.py`
- Create: `backend/src/protocol_poc/export/routes.py`
- Create: `backend/migrations/versions/0007_exports.py`
- Test: `backend/tests/unit/export/test_gate.py`
- Test: `backend/tests/integration/export/test_snapshot.py`

- [ ] **Step 1: Write failing gate tests**

```python
@pytest.mark.parametrize("blocker", [
    "UNSUPPORTED_CONTENT", "UNRESOLVED_CRITICAL_FACT", "CRITICAL_CONTRADICTION",
    "INCOMPLETE_PROVENANCE", "REQUIRED_PLACEHOLDER", "VALIDATION_INCOMPLETE",
    "STALE_PASSAGE",
])
def test_each_hard_blocker_denies_export(gate, valid_state, blocker):
    valid_state.add_blocker(blocker)
    decision = gate.evaluate(valid_state)
    assert decision.allowed is False
    assert blocker in decision.blocker_codes


def test_validator_exception_denies_export(gate, state_with_validator_exception):
    assert gate.evaluate(state_with_validator_exception).allowed is False
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/export tests/integration/export -v`  
Expected: FAIL.

- [ ] **Step 3: Implement one-way snapshot creation**

Within a serializable transaction: lock the study version, rerun mandatory validation, calculate scorecard, evaluate the hard gate, and if allowed create immutable `ExportSnapshot`, `SnapshotFact`, `SnapshotPassage`, `SnapshotGuidance`, `SnapshotTemplate`, and `SnapshotFinding` records. Persist source version IDs and hashes. Denied attempts append an audit event but create no snapshot.

- [ ] **Step 4: Verify race and tamper cases**

Add tests where a fact changes during snapshot creation and where a stored artifact hash is altered. Run: `uv run pytest tests/unit/export tests/integration/export -v`  
Expected: PASS; the first retries/denies and the second fails integrity verification.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/export backend/migrations backend/tests
git commit -m "feat: add immutable gated export snapshots"
```

### Task 13: Render deterministic Word and traceability artifacts

**Files:**
- Create: `backend/src/protocol_poc/rendering/template_map.py`
- Create: `backend/src/protocol_poc/rendering/docx_renderer.py`
- Create: `backend/src/protocol_poc/rendering/traceability.py`
- Create: `backend/src/protocol_poc/rendering/artifact_service.py`
- Test: `backend/tests/unit/rendering/test_template_map.py`
- Test: `backend/tests/integration/rendering/test_artifacts.py`

- [ ] **Step 1: Write failing deterministic-render tests**

```python
def test_same_snapshot_and_renderer_version_produce_same_document_xml(renderer, snapshot):
    first = canonical_docx_xml(renderer.render(snapshot))
    second = canonical_docx_xml(renderer.render(snapshot))
    assert first == second


def test_ambiguous_insertion_point_blocks_render(renderer, ambiguous_template, snapshot):
    with pytest.raises(TemplateMappingError, match="ambiguous"):
        renderer.render(snapshot, ambiguous_template)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/rendering tests/integration/rendering -v`  
Expected: FAIL.

- [ ] **Step 3: Implement explicit template mapping**

Use content controls/bookmarks or uniquely named headings as allowlisted insertion points. Preserve unaffected body elements, section properties, headers, footers, styles, and numbering. Refuse missing or duplicate targets. Strip volatile package metadata before hashing. Do not call the AI gateway from rendering code.

- [ ] **Step 4: Generate the artifact set from one snapshot**

Create DOCX, traceability CSV/JSON, and scorecard JSON/HTML artifacts with the same snapshot ID, renderer version, SHA-256, and timestamp. Traceability rows contain section, passage, claim, fact value, evidence location, guidance release, review state, and validation status. Run: `uv run pytest tests/unit/rendering tests/integration/rendering -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/rendering backend/tests
git commit -m "feat: render deterministic protocol export artifacts"
```

### Task 14: Build Guided Review and Model Explorer UI

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/app/studies/[studyId]/review/page.tsx`
- Create: `frontend/src/features/review/ReviewQueue.tsx`
- Create: `frontend/src/features/review/EvidenceComparison.tsx`
- Create: `frontend/src/app/studies/[studyId]/model/page.tsx`
- Create: `frontend/src/features/model/ModelExplorer.tsx`
- Test: `frontend/tests/review/ReviewQueue.test.tsx`
- Test: `frontend/tests/model/ModelExplorer.test.tsx`

- [ ] **Step 1: Write failing component tests**

```tsx
it("keeps blockers visible and requires confirmation for a critical fact", async () => {
  render(<ReviewQueue studyId="study-1" api={criticalFactApi} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Export blocked");
  await userEvent.click(screen.getByRole("button", { name: "Approve fact" }));
  expect(screen.getByLabelText("I explicitly confirm this critical fact")).toBeRequired();
});
```

- [ ] **Step 2: Run tests**

Run: `cd frontend && npm test -- --run`  
Expected: FAIL because the components do not exist.

- [ ] **Step 3: Implement accessible review UI**

Show blocker banner, ordered review queue, source/candidate comparison, exact evidence location, confidence as secondary metadata, downstream impact, and approve/edit/reject/defer actions. Critical approval requires a fresh checked confirmation and version token. Never hide blockers behind collapsed panels.

- [ ] **Step 4: Implement Model Explorer**

Show facts, provenance, relationships, versions, conflicts, status, and affected passages. Add keyboard navigation, focus management, WCAG AA contrast, and textual alternatives for relationship graphs. Run: `npm test -- --run && npm run typecheck`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src frontend/tests
git commit -m "feat: add guided fact review and model explorer"
```

### Task 15: Build passage authoring, impact, and export UI

**Files:**
- Create: `frontend/src/app/studies/[studyId]/draft/page.tsx`
- Create: `frontend/src/features/drafting/ProtocolNavigator.tsx`
- Create: `frontend/src/features/drafting/PassageEditor.tsx`
- Create: `frontend/src/features/drafting/EvidencePanel.tsx`
- Create: `frontend/src/features/drafting/ImpactPanel.tsx`
- Create: `frontend/src/features/quality/Scorecard.tsx`
- Create: `frontend/src/features/export/ExportPanel.tsx`
- Test: `frontend/tests/drafting/PassageEditor.test.tsx`
- Test: `frontend/tests/export/ExportPanel.test.tsx`

- [ ] **Step 1: Write failing authoring tests**

```tsx
it("prevents acceptance when a claim is unsupported", async () => {
  render(<PassageEditor passage={blockedPassage} api={api} />);
  expect(screen.getByText("Unsupported dose: 20 mg")).toBeVisible();
  expect(screen.getByRole("button", { name: "Accept passage" })).toBeDisabled();
});


it("shows dimensions without an overall percentage", () => {
  render(<Scorecard card={scorecard} />);
  expect(screen.queryByText(/overall/i)).not.toBeInTheDocument();
  expect(screen.getByText("Traceability")).toBeVisible();
});
```

- [ ] **Step 2: Run tests**

Run: `cd frontend && npm test -- --run`  
Expected: FAIL.

- [ ] **Step 3: Implement passage-level authoring**

Provide scoped section navigation, editor, evidence/guidance support panel, finding list, impact list, and accept/edit/reject/regenerate actions. Stale passages are visually distinct and non-accepting until revalidated. Preserve unsaved editor text on validation errors.

- [ ] **Step 4: Implement scorecard and gated export panel**

Show the six dimensions, counts, findings, disclaimer, and all blockers. The export button is convenience-only; the API remains authoritative. After success, show artifact names, hashes, and shared snapshot ID. Run: `npm test -- --run && npm run typecheck`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src frontend/tests
git commit -m "feat: add reviewed drafting and gated export UI"
```

### Task 16: Build the synthetic gold standard and adversarial safety suite

**Files:**
- Create: `fixtures/synthetic-study/synopsis.docx`
- Create: `fixtures/synthetic-study/template.docx`
- Create: `fixtures/synthetic-study/gold-facts.json`
- Create: `fixtures/synthetic-study/gold-traceability.json`
- Create: `fixtures/synthetic-study/scenarios/*.json`
- Create: `backend/tests/evaluation/test_gold_standard.py`
- Create: `backend/tests/evaluation/test_adversarial_exports.py`
- Create: `backend/tests/evaluation/conftest.py`

- [ ] **Step 1: Encode the approved synthetic reference contract**

`gold-facts.json` must contain stable IDs for study identity, objectives, endpoints, Week 24 timepoint, arms, interventions, dose/unit, population, and eligibility facts plus exact synopsis locations. Have a qualified medical writer approve this fixture outside the test code and record reviewer/date/version metadata in the JSON.

- [ ] **Step 2: Write the failing adversarial matrix**

```python
@pytest.mark.parametrize("scenario,expected", [
    ("missing_dose", "REQUIRED_PLACEHOLDER"),
    ("contradictory_endpoints", "CRITICAL_CONTRADICTION"),
    ("ambiguous_timepoint", "UNRESOLVED_CRITICAL_FACT"),
    ("unsupported_eligibility", "UNSUPPORTED_CONTENT"),
    ("irrelevant_guidance", "APPROVED_GUIDANCE_COVERAGE_INCOMPLETE"),
    ("prompt_injection", "UNTRUSTED_INSTRUCTION_IGNORED"),
    ("plausible_absent_fact", "UNSUPPORTED_CONTENT"),
])
def test_scenario_cannot_export_unsupported_content(evaluation_runner, scenario, expected):
    result = evaluation_runner.run(scenario)
    assert result.exported_unsupported_clinical_fact_count == 0
    assert expected in result.finding_codes
```

- [ ] **Step 3: Run the suite and observe failures before fixture responses are added**

Run: `cd backend && uv run pytest tests/evaluation -v`  
Expected: FAIL with missing scenario fixtures or mismatched expected blockers.

- [ ] **Step 4: Add deterministic scenario responses and satisfy the safety contract**

Add changed-fact invalidation, stale guidance, malformed model output, ambiguous template, validator outage, and concurrent fact-edit cases. Run: `uv run pytest tests/evaluation -v`  
Expected: PASS and summary reports `unsupported clinical facts exported: 0`.

- [ ] **Step 5: Commit**

```bash
git add fixtures backend/tests/evaluation
git commit -m "test: add synthetic protocol safety evaluation suite"
```

### Task 17: Add full-path browser tests

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/tests/e2e/happy-path.spec.ts`
- Create: `frontend/tests/e2e/blocked-export.spec.ts`
- Create: `frontend/tests/e2e/fact-change-invalidation.spec.ts`

- [ ] **Step 1: Write the failing happy-path test**

```ts
test("writer reviews facts, accepts passages, and exports one snapshot", async ({ page }) => {
  await page.goto("/studies/synthetic-phase-2/review");
  await reviewAllRequiredFacts(page);
  await page.goto("/studies/synthetic-phase-2/draft");
  await acceptAllValidPassages(page);
  await page.getByRole("button", { name: "Create export" }).click();
  const snapshot = await page.getByTestId("snapshot-id").textContent();
  await expect(page.getByText("protocol.docx")).toBeVisible();
  await expect(page.getByText("traceability.csv")).toBeVisible();
  await expect(page.getByText("scorecard.html")).toBeVisible();
  await expect(page.getByTestId("artifact-snapshot-ids")).toContainText(snapshot!);
});
```

- [ ] **Step 2: Run browser tests**

Run: `make up && cd frontend && npx playwright test`  
Expected: FAIL until helpers and seeded API state exist.

- [ ] **Step 3: Add deterministic seed/reset endpoints for test environment only**

Expose reset/seed endpoints only when `APP_ENV=test`; production/local demo configuration must return 404. Add Playwright helpers for explicit fact confirmation and passage review.

- [ ] **Step 4: Verify three critical journeys**

The blocked-export test introduces an unsupported eligibility claim and confirms server rejection. The invalidation test changes dose after passage acceptance and confirms stale status plus export denial. Run: `npx playwright test`  
Expected: all three tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/playwright.config.ts frontend/tests/e2e backend/src backend/tests
git commit -m "test: verify writer and export journeys end to end"
```

### Task 18: Complete safety documentation and release verification

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/safety-case.md`
- Create: `docs/demo-script.md`
- Modify: `README.md`
- Modify: `Makefile`
- Test: `backend/tests/evaluation/test_documented_controls.py`

- [ ] **Step 1: Write a failing invariant-to-control documentation test**

```python
def test_every_safety_invariant_has_control_test_and_owner(safety_case):
    required = {
        "no_unsupported_export", "critical_fact_confirmation", "claim_provenance",
        "fact_change_invalidation", "validator_failure_closed", "tenant_isolation"
    }
    assert required <= set(safety_case.control_ids)
    assert all(c.test_ids and c.module_owner for c in safety_case.controls)
```

- [ ] **Step 2: Run the documentation test**

Run: `cd backend && uv run pytest tests/evaluation/test_documented_controls.py -v`  
Expected: FAIL because the safety-case control table is absent.

- [ ] **Step 3: Document architecture, safety claims, limitations, and demo**

The safety case maps each invariant to preventive controls, detective controls, tests, residual limitations, and owning module. The README must say synthetic data only, no live drafting research, no clinical/regulatory/submission-readiness claim, and not a validated system. The demo script must include both successful export and blocked adversarial scenarios.

- [ ] **Step 4: Run the full release verification**

Run:

```bash
make lint
make typecheck
make test
make evaluation
make e2e
```

Expected: every command exits 0; the evaluation summary states `unsupported clinical facts exported: 0`; all hard-blocker scenarios deny export; no composite readiness score is present.

- [ ] **Step 5: Inspect generated artifacts manually**

Open the DOCX, traceability CSV, and scorecard HTML from the happy-path snapshot. Confirm section placement, styles, headers/footers, claim rows, evidence locations, shared snapshot ID, disclaimers, and absence of unresolved placeholders. Record the artifact hashes and inspection result in the release checklist.

- [ ] **Step 6: Commit**

```bash
git add README.md Makefile docs backend/tests/evaluation
git commit -m "docs: complete POC safety case and release checks"
```

## 5. Implementation order and checkpoints

Execute tasks strictly in order unless a reviewed plan amendment says otherwise. Stop for user review after these checkpoints:

- **Checkpoint A — after Task 3:** stack starts; DOCX ingestion is bounded, versioned, and auditable.
- **Checkpoint B — after Task 6:** writer can review candidates and build an approved canonical model.
- **Checkpoint C — after Task 10:** governed passage drafting, deterministic validation, and invalidation work end to end.
- **Checkpoint D — after Task 13:** server-side gate produces the three snapshot-linked artifacts.
- **Checkpoint E — after Task 18:** UI, adversarial evaluation, documentation, and release evidence are complete.

At each checkpoint, demonstrate behavior with synthetic fixtures, report verification output, list known limitations, and obtain approval before proceeding to the next increment.

## 6. Requirement-to-task coverage

| Approved design requirement | Implementing tasks |
|---|---|
| Versioned synopsis/template ingest with source locations | 3 |
| Four separated content states | 4–6, 8, 10 |
| Critical-fact explicit confirmation | 6, 14 |
| Canonical model and explicit relationships | 4 |
| Approved, versioned guidance only | 7 |
| Controlled schema-constrained AI tasks | 5, 8 |
| No live drafting research / prompt-injection defense | 5, 7, 16 |
| Independent deterministic fact/provenance checks | 9 |
| Drafting model cannot certify itself | 9–12 |
| Passage review and change invalidation | 10, 15, 17 |
| Hard export blockers and fail-closed outages | 11–12, 16 |
| Separate scorecard dimensions, no composite/readiness claim | 11, 15 |
| Deterministic Word renderer | 13 |
| Traceability and shared export snapshot | 12–13 |
| Append-only audit trail | 2–13 |
| Tenant/sponsor isolation | 2, 7, 16 |
| Guided Review, Model Explorer, authoring workspace | 14–15 |
| Governed learning layers and no automatic learning | 7, documentation in 18 |
| Gold standard and named adversarial cases | 16–17 |
| Zero unsupported clinical facts in exports | 9, 12, 16, 18 |
| Synthetic-only and bounded POC disclaimers | 1, 11, 18 |

## 7. Risks and explicit mitigations

- **DOCX variability:** bound the POC to one approved template family; reject ambiguous mappings instead of guessing.
- **Claim extraction uncertainty:** uncertainty is a blocker; deterministic clinical-value checks do not rely on the drafting model's self-report.
- **Model/provider drift:** fixture provider is the safety baseline; real-provider adapters require contract and evaluation parity before activation.
- **Writer burden:** prioritize review by criticality and impact, but never auto-approve critical facts or hide blockers.
- **False confidence from scorecards:** prohibit a composite score and readiness language in schemas, tests, and UI copy.
- **Race conditions:** immutable snapshots use serializable transactions, version preconditions, and artifact hashes.
- **Cross-tenant leakage:** tenant-aware keys, repository guards, retrieval filters, contract tests, and no shared sponsor patterns.
- **Evaluation overfitting:** retain a reviewed gold set plus mutation/property tests and withheld adversarial variants.

## 8. Plan review gate

No implementation begins until the user approves this plan and chooses an execution mode. Any requested change to the approved design must first update the design specification, then this plan and its coverage matrix.
