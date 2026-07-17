from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.studies.models import Study, now
from protocol_poc.studies.repository import StudyRepository
from protocol_poc.tenancy import TenantContext, require_tenant_context


class StudyError(Exception):
    """Base class for study lifecycle errors."""


class StudyVersionConflict(StudyError):
    """The supplied optimistic version is stale."""


class StudyArchived(StudyError):
    """The requested mutation is forbidden for an archived study."""


class StudyNotFound(StudyError):
    """The study is absent or inaccessible to the tenant."""


class StudyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = StudyRepository(session)
        self.audit = AuditService(session)

    def create(self, ctx: TenantContext, name: str) -> Study:
        context = require_tenant_context(ctx)
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("study name must not be blank")
        if len(normalized_name) > 255:
            raise ValueError("study name must be at most 255 characters")
        timestamp = now()
        study = Study(
            tenant_id=context.tenant_id,
            name=normalized_name,
            lifecycle="active",
            version=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.repository.add(study)
        self.session.flush()
        self.audit.append(context, "study.created", "study", study.id, {"version": study.version})
        return study

    def list(self, ctx: TenantContext, lifecycle: str) -> list[Study]:
        context = require_tenant_context(ctx)
        if lifecycle not in {"active", "archived"}:
            raise ValueError("invalid study lifecycle")
        return self.repository.list(context, lifecycle)

    def get(self, ctx: TenantContext, study_id: str) -> Study:
        context = require_tenant_context(ctx)
        study = self.repository.get(context, study_id)
        if study is None:
            raise StudyNotFound("study not found")
        return study

    def require_active(self, ctx: TenantContext, study_id: str) -> Study:
        study = self.get(ctx, study_id)
        if study.lifecycle == "archived":
            raise StudyArchived("study is archived")
        return study

    def archive(self, ctx: TenantContext, study_id: str, expected_version: int) -> Study:
        context = require_tenant_context(ctx)
        study = self.get(context, study_id)
        self._require_version(study, expected_version)
        if study.lifecycle == "archived":
            raise StudyArchived("study is archived")
        timestamp = now()
        transitioned = self.repository.transition(
            context,
            study.id,
            expected_version=expected_version,
            current_lifecycle="active",
            next_lifecycle="archived",
            updated_at=timestamp,
            archived_at=timestamp,
        )
        if not transitioned:
            self._refresh_after_failed_transition(study)
            self._require_version(study, expected_version)
            raise StudyArchived("study is archived")
        self.session.expire(study)
        self.session.refresh(study)
        self.audit.append(context, "study.archived", "study", study.id, {"version": study.version})
        self.session.flush()
        return study

    def restore(self, ctx: TenantContext, study_id: str, expected_version: int) -> Study:
        context = require_tenant_context(ctx)
        study = self.get(context, study_id)
        self._require_version(study, expected_version)
        if study.lifecycle != "archived":
            raise StudyVersionConflict("study is already active")
        transitioned = self.repository.transition(
            context,
            study.id,
            expected_version=expected_version,
            current_lifecycle="archived",
            next_lifecycle="active",
            updated_at=now(),
            archived_at=None,
        )
        if not transitioned:
            self._refresh_after_failed_transition(study)
            self._require_version(study, expected_version)
            raise StudyVersionConflict("study is already active")
        self.session.expire(study)
        self.session.refresh(study)
        self.audit.append(context, "study.restored", "study", study.id, {"version": study.version})
        self.session.flush()
        return study

    def _refresh_after_failed_transition(self, study: Study) -> None:
        self.session.expire(study)
        self.session.refresh(study)

    @staticmethod
    def _require_version(study: Study, expected_version: int) -> None:
        if study.version != expected_version:
            raise StudyVersionConflict(
                f"expected version {expected_version}, found {study.version}"
            )
