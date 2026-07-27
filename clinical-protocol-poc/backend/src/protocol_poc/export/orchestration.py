from dataclasses import dataclass
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.drafting.models import Claim, PassageVersion, SupportLink
from protocol_poc.export.artifact_service import ArtifactDescriptor, ExportArtifactRepository
from protocol_poc.export.models import ExportSnapshot, SnapshotFact, SnapshotPassage
from protocol_poc.export.service import ExportService
from protocol_poc.files.models import SourceEvidence
from protocol_poc.files.service import FileStorage
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
    storage_keys: tuple[str, ...] = ()


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
        build = ExportService(self._session).create_snapshot_build(
            context,
            study_id,
            expected_study_version=command.expected_study_version,
            template_version_id=command.template_version_id,
            template_hash=command.template_hash,
            renderer_version=self._renderer_version,
        )
        template = self._storage.get(build.template_version.storage_key)
        if template is None:
            raise OSError("template storage object is missing")
        render_snapshot = self._render_snapshot(context, build.snapshot)
        rendered = ArtifactService(self._renderer_version).create(
            render_snapshot, build.scorecard, template
        )
        persisted = ExportArtifactRepository(self._session, self._storage).persist(
            context, build.snapshot, rendered
        )
        return ExportResult(
            build.snapshot.id, persisted.descriptors, persisted.written_storage_keys
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
        snapshot_facts = {
            item.source_fact_id: item
            for item in self._session.scalars(
                select(SnapshotFact).where(
                    SnapshotFact.tenant_id == ctx.tenant_id,
                    SnapshotFact.snapshot_id == snapshot.id,
                )
            )
        }
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
            frozen_facts = [
                snapshot_facts[fact_id]
                for fact_id in fact_ids
                if fact_id in snapshot_facts
            ]
            version_history = list(self._session.scalars(
                select(FactVersion).where(
                    FactVersion.tenant_id == ctx.tenant_id,
                    FactVersion.fact_id.in_(fact_ids),
                )
            )) if fact_ids else []
            versions_by_source = {
                (version.fact_id, version.version): version
                for version in version_history
            }
            facts = [
                versions_by_source[(fact.source_fact_id, fact.source_version)]
                for fact in frozen_facts
                if (fact.source_fact_id, fact.source_version) in versions_by_source
            ]
            fact_value = "; ".join(
                json.dumps(fact.value_json, sort_keys=True, separators=(",", ":"))
                for fact in frozen_facts
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
