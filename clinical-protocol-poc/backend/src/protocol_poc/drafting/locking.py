from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.drafting.models import Passage
from protocol_poc.studies.models import Study
from protocol_poc.studies.service import StudyArchived, StudyNotFound
from protocol_poc.tenancy import TenantContext


class PassageReviewError(RuntimeError):
    pass


class PassageVersionConflict(PassageReviewError):
    pass


def lock_active_passage(
    session: Session,
    ctx: TenantContext,
    passage_id: str,
    expected_version: int,
) -> Passage:
    study_id = session.scalar(
        select(Passage.study_id).where(
            Passage.id == passage_id,
            Passage.tenant_id == ctx.tenant_id,
        )
    )
    if study_id is None:
        raise PassageReviewError("passage not found")

    study = session.scalar(
        select(Study)
        .where(Study.id == study_id, Study.tenant_id == ctx.tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if study is None:
        raise StudyNotFound("study not found")
    if study.lifecycle == "archived":
        raise StudyArchived("study is archived")

    passage = session.scalar(
        select(Passage)
        .where(
            Passage.id == passage_id,
            Passage.tenant_id == ctx.tenant_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if passage is None:
        raise PassageReviewError("passage not found")
    if passage.current_version != expected_version:
        raise PassageVersionConflict("passage version changed")
    return passage
