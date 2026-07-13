from dataclasses import dataclass
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.drafting.models import Claim, PassageVersion, SupportLink
from protocol_poc.export.artifact_service import ArtifactDescriptor, ExportArtifactRepository
from protocol_poc.export.models import ExportSnapshot, SnapshotPassage
from protocol_poc.export.service import ExportDenied, ExportService
from protocol_poc.files.models import FileRecord, FileVersion, SourceEvidence
from protocol_poc.files.service import FileStorage
from protocol_poc.quality.service import QualityService
from protocol_poc.rendering.artifact_service import ArtifactService
from protocol_poc.rendering.docx_renderer import RenderSnapshot
from protocol_poc.studies.models import FactVersion
from protocol_poc.tenancy import TenantContext, require_tenant_context


@dataclass(frozen=True)
class ExportCommand:
    expected_study_version: int
    template_version_id: str
    template_hash: str


@dataclass(frozen=True)
class ExportResult:
    snapshot_id: str
    artifacts: tuple[ArtifactDescriptor, ...]


class ExportOrchestrator:
    def __init__(
        self,
        session: Session,
        storage: FileStorage,
        renderer_version: str,
    ) -> None:
        self._session = session
        self._storage = storage
        self._renderer_version = renderer_version

    def create(
        self,
        ctx: TenantContext,
        study_id: str,
        command: ExportCommand,
    ) -> ExportResult:
        context = require_tenant_context(ctx)
        template_version = self._template_version(
            context, study_id, command.template_version_id
        )
        if template_version is None:
            raise ExportDenied(("TEMPLATE_VERSION_INVALID",))
        if template_version.checksum_sha256 != command.template_hash:
            raise ExportDenied(("TEMPLATE_HASH_MISMATCH",))
        template = self._storage.get(template_version.storage_key)
        if template is None:
            raise ExportDenied(("TEMPLATE_VERSION_INVALID",))

        scorecard = QualityService(self._session).calculate(context, study_id)
        snapshot = ExportService(self._session).create_snapshot(
            context,
            study_id,
            expected_study_version=command.expected_study_version,
            template_version_id=template_version.id,
            template_hash=template_version.checksum_sha256,
            renderer_version=self._renderer_version,
        )
        render_snapshot = self._render_snapshot(context, snapshot)
        rendered = ArtifactService(self._renderer_version).create(
            render_snapshot, scorecard, template
        )
        descriptors = ExportArtifactRepository(self._session, self._storage).persist(
            context, snapshot, rendered
        )
        return ExportResult(snapshot.id, descriptors)

    def _template_version(
        self,
        ctx: TenantContext,
        study_id: str,
        version_id: str,
    ) -> FileVersion | None:
        return self._session.scalar(
            select(FileVersion)
            .join(
                FileRecord,
                (FileRecord.id == FileVersion.file_record_id)
                & (FileRecord.tenant_id == FileVersion.tenant_id),
            )
            .where(
                FileVersion.id == version_id,
                FileVersion.tenant_id == ctx.tenant_id,
                FileRecord.study_id == study_id,
                FileRecord.role == "template",
            )
        )

    def _render_snapshot(
        self,
        ctx: TenantContext,
        snapshot: ExportSnapshot,
    ) -> RenderSnapshot:
        snapshot_passages = list(self._session.scalars(
            select(SnapshotPassage).where(
                SnapshotPassage.tenant_id == ctx.tenant_id,
                SnapshotPassage.snapshot_id == snapshot.id,
            )
        ))
        passages = {item.section: item.text for item in snapshot_passages}
        rows: list[dict[str, str]] = []
        for item in snapshot_passages:
            version = self._session.scalar(
                select(PassageVersion).where(
                    PassageVersion.tenant_id == ctx.tenant_id,
                    PassageVersion.passage_id == item.source_passage_id,
                    PassageVersion.version == item.source_version,
                )
            )
            if version is None:
                continue
            saved_claims = list(self._session.scalars(
                select(Claim).where(
                    Claim.tenant_id == ctx.tenant_id,
                    Claim.passage_version_id == version.id,
                )
            ))
            claims: list[Claim | None] = list(saved_claims)
            if not claims:
                claims.append(None)
            links = list(self._session.scalars(
                select(SupportLink).where(
                    SupportLink.tenant_id == ctx.tenant_id,
                    SupportLink.passage_version_id == version.id,
                )
            ))
            fact_ids = [link.support_id for link in links if link.support_type == "fact"]
            guidance_ids = [link.support_id for link in links if link.support_type == "guidance"]
            facts = list(self._session.scalars(
                select(FactVersion).where(
                    FactVersion.tenant_id == ctx.tenant_id,
                    FactVersion.fact_id.in_(fact_ids),
                    FactVersion.is_current.is_(True),
                )
            )) if fact_ids else []
            fact_value = "; ".join(
                json.dumps(fact.value_json, sort_keys=True, separators=(",", ":"))
                for fact in facts
            )
            evidence_location = self._evidence_locations(ctx, facts)
            for claim in claims:
                rows.append({
                    "section": item.section,
                    "passage": item.text,
                    "claim": claim.text if claim is not None else "",
                    "fact_value": fact_value,
                    "evidence_location": evidence_location,
                    "guidance_release": "; ".join(sorted(guidance_ids)),
                    "review_state": item.review_state,
                    "validation_status": "pass",
                })
        return RenderSnapshot(snapshot.id, passages, rows)

    def _evidence_locations(
        self,
        ctx: TenantContext,
        facts: list[FactVersion],
    ) -> str:
        evidence_ids = [fact.source_evidence_id for fact in facts if fact.source_evidence_id]
        if not evidence_ids:
            return ""
        evidence = list(self._session.scalars(
            select(SourceEvidence).where(
                SourceEvidence.tenant_id == ctx.tenant_id,
                SourceEvidence.id.in_(evidence_ids),
            )
        ))
        return "; ".join(
            json.dumps(item.location_json, sort_keys=True, separators=(",", ":"))
            for item in evidence
        )
