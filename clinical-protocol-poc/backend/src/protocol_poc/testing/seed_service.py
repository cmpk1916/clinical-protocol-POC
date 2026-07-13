from hashlib import sha256

from sqlalchemy.orm import Session

from protocol_poc.drafting.models import Claim, Passage, PassageVersion, SupportLink
from protocol_poc.files.models import FileRecord, FileVersion, SourceEvidence
from protocol_poc.files.service import FileStorage
from protocol_poc.rendering.template_map import build_template
from protocol_poc.studies.models import Fact, FactVersion, Study


SECTIONS = ("synopsis", "objectives_endpoints", "study_design", "eligibility")


def seed_synthetic_study(
    session: Session,
    storage: FileStorage,
    study_id: str,
    scenario: str,
) -> dict[str, object]:
    tenant_id = "synthetic-demo"
    session.add(Study(
        id=study_id,
        tenant_id=tenant_id,
        name="Synthetic Phase II type 2 diabetes study",
        version=1,
    ))
    session.flush()

    source_document = build_template(["synopsis"])
    source_hash = sha256(source_document).hexdigest()
    source_key = f"test/{study_id}/synthetic-synopsis.docx"
    source_text = "Synopsis p. 4 supports a dose of 10 mg once daily."
    storage.put(source_key, source_document)
    session.add(FileRecord(
        id="synopsis-file", tenant_id=tenant_id, study_id=study_id, role="synopsis",
    ))
    session.flush()
    session.add(FileVersion(
        id="synopsis-v1",
        tenant_id=tenant_id,
        file_record_id="synopsis-file",
        version=1,
        display_filename="synthetic-synopsis.docx",
        checksum_sha256=source_hash,
        size_bytes=len(source_document),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        storage_key=source_key,
        status="succeeded",
    ))
    session.flush()
    session.add(SourceEvidence(
        id="evidence-dose",
        tenant_id=tenant_id,
        file_version_id="synopsis-v1",
        ordinal=0,
        location_json={"filename": "synthetic-synopsis.docx", "paragraph": 4},
        text=source_text,
        text_sha256=sha256(source_text.encode()).hexdigest(),
    ))
    session.flush()

    session.add(Fact(
        id="fact-dose", tenant_id=tenant_id, study_id=study_id, kind="dose",
        status="approved", critical=True,
    ))
    session.flush()
    session.add(FactVersion(
        id="fact-dose-v1", tenant_id=tenant_id, fact_id="fact-dose", version=1,
        value_json={"kind": "dose", "value": "10", "unit": "mg", "frequency": "once daily"},
        source_evidence_id="evidence-dose", is_current=True,
    ))

    for section in SECTIONS:
        passage_id = f"passage-{section}"
        version_id = f"passage-version-{section}"
        is_stale = scenario == "fact_change_invalidation" and section == "study_design"
        is_unsupported = scenario == "unsupported_eligibility" and section == "eligibility"
        session.add(Passage(
            id=passage_id,
            tenant_id=tenant_id,
            study_id=study_id,
            section=section,
            status="stale" if is_stale else ("blocked" if is_unsupported else "accepted"),
            invalidation_reason="supporting_fact_changed" if is_stale else None,
        ))
        session.flush()
        text = {
            "synopsis": "This synthetic Phase II study evaluates study treatment in adults with type 2 diabetes mellitus.",
            "objectives_endpoints": "The primary objective evaluates change from baseline at Week 24.",
            "study_design": "Participants receive 10 mg once daily in the synthetic study.",
            "eligibility": "Adults with type 2 diabetes mellitus may be eligible under the synthetic criteria.",
        }[section]
        session.add(PassageVersion(
            id=version_id,
            tenant_id=tenant_id,
            passage_id=passage_id,
            version=1,
            text=text,
            placeholders=["unsupported eligibility criterion"] if is_unsupported else [],
            is_current=True,
        ))
        session.flush()
        session.add(Claim(
            tenant_id=tenant_id,
            passage_version_id=version_id,
            text=text,
            metadata_json={"validation_status": "pass" if not is_unsupported else "blocked"},
        ))
        session.add(SupportLink(
            tenant_id=tenant_id,
            passage_version_id=version_id,
            support_type="fact",
            support_id="fact-dose",
        ))

    template = build_template(list(SECTIONS))
    template_hash = sha256(template).hexdigest()
    template_key = f"test/{study_id}/template-v1.docx"
    storage.put(template_key, template)
    session.add(FileRecord(
        id="template-file", tenant_id=tenant_id, study_id=study_id, role="template",
    ))
    session.flush()
    session.add(FileVersion(
        id="template-v1",
        tenant_id=tenant_id,
        file_record_id="template-file",
        version=1,
        display_filename="synthetic-protocol-template.docx",
        checksum_sha256=template_hash,
        size_bytes=len(template),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        storage_key=template_key,
        status="succeeded",
    ))
    session.flush()
    return {
        "expectedStudyVersion": 1,
        "templateVersionId": "template-v1",
        "templateHash": template_hash,
    }
