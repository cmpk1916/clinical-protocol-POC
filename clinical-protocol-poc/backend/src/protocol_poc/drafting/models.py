from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from protocol_poc.common.ids import new_id
from protocol_poc.db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class Passage(Base):
    __tablename__ = "passages"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_passage_id_tenant"),
        UniqueConstraint("tenant_id", "study_id", "section", name="uq_passage_study_section_tenant"),
        ForeignKeyConstraint(["study_id", "tenant_id"], ["studies.id", "studies.tenant_id"], name="fk_passage_study_tenant"),
        CheckConstraint("section IN ('synopsis','objectives_endpoints','study_design','eligibility')", name="ck_passage_section"),
        CheckConstraint("status IN ('draft','blocked','ready_for_review','accepted','rejected','stale')", name="ck_passage_status"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    study_id: Mapped[str] = mapped_column(String(128), nullable=False)
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    invalidation_reason: Mapped[str | None] = mapped_column(String(128))


class PassageVersion(Base):
    __tablename__ = "passage_versions"
    __table_args__ = (
        UniqueConstraint("passage_id", "version", name="uq_passage_version_number"),
        UniqueConstraint("id", "tenant_id", name="uq_passage_version_id_tenant"),
        ForeignKeyConstraint(["passage_id", "tenant_id"], ["passages.id", "passages.tenant_id"], name="fk_passage_version_passage_tenant"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    passage_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    placeholders: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        ForeignKeyConstraint(["passage_version_id", "tenant_id"], ["passage_versions.id", "passage_versions.tenant_id"], name="fk_claim_passage_version_tenant"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    passage_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class SupportLink(Base):
    __tablename__ = "support_links"
    __table_args__ = (
        ForeignKeyConstraint(["passage_version_id", "tenant_id"], ["passage_versions.id", "passage_versions.tenant_id"], name="fk_support_passage_version_tenant"),
        CheckConstraint("support_type IN ('fact','guidance')", name="ck_support_type"),
        UniqueConstraint("passage_version_id", "support_type", "support_id", name="uq_support_link"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    passage_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    support_type: Mapped[str] = mapped_column(String(16), nullable=False)
    support_id: Mapped[str] = mapped_column(String(128), nullable=False)
