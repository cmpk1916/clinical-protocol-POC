# Safety Case

## Claim

Within the synthetic fixture boundary, the POC fails closed when required evidence, review, validation, guidance coverage, version consistency, or deterministic rendering conditions are not satisfied. This is a software control claim only, not a clinical or regulatory claim.

## Control map

The table format is checked automatically. Test identifiers point to executable evidence in this repository.

| Control ID | Preventive control | Detective control | Module owner | Test IDs | Residual limitation |
| --- | --- | --- | --- | --- | --- |
| `no_unsupported_export` | Closed-world drafting context and authoritative server export gate | Claim validation and adversarial export evaluation | `protocol_poc.export` | `tests/unit/export/test_gate.py`, `tests/evaluation/test_adversarial_exports.py` | Fixture coverage cannot prove absence of all unsupported content patterns. |
| `critical_fact_confirmation` | Critical fact approval requires explicit fresh confirmation and a version token | Guided Review component and review-service tests | `protocol_poc.review` | `frontend/tests/review/ReviewQueue.test.tsx`, `tests/unit/review/test_fact_review.py` | POC identity and workflow controls are not validated for regulated use. |
| `claim_provenance` | Drafting context contains approved facts and evidence locations only | Traceability artifacts and claim validators expose unsupported claims | `protocol_poc.validation` | `tests/integration/validation/test_passage_validation.py`, `tests/integration/rendering/test_artifacts.py` | Evidence correctness still requires qualified human review. |
| `fact_change_invalidation` | Passage dependencies store fact versions | Fact edits mark dependent passages stale and deny export | `protocol_poc.drafting` | `tests/integration/review/test_invalidation.py`, `frontend/tests/e2e/fact-change-invalidation.spec.ts` | Dependency declarations may be incomplete outside the synthetic contract. |
| `validator_failure_closed` | Export requires a successful deterministic validator result | Validator outage scenario denies export | `protocol_poc.validation` | `tests/evaluation/test_adversarial_exports.py`, `tests/unit/export/test_gate.py` | Availability and recovery behavior are not production-hardened. |
| `tenant_isolation` | Tenant context scopes persistence and identity verification | Tenant/audit tests detect cross-tenant or unsigned access | `protocol_poc.tenancy` | `tests/unit/test_identity.py`, `tests/integration/test_audit_append_only.py` | POC deployment and database policies are not a production authorization model. |

## Evaluation evidence

- The synthetic gold contract covers identity, objectives, endpoints, Week 24, arms, interventions, dose/unit/frequency, population, and eligibility.
- Thirteen adversarial scenarios deny export.
- The evaluation invariant is `unsupported clinical facts exported: 0`.
- Browser journeys cover successful snapshot export, unsupported eligibility blocking, and dose-change invalidation.
- Quality is reported by six dimensions; there is no composite readiness percentage.

## Non-claims

This safety case does not claim that the POC is validated, clinically safe, regulatorily acceptable, secure for production, submission ready, or suitable for autonomous decision-making.
