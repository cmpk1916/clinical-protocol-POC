from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from protocol_poc.common.ids import new_id
from protocol_poc.db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class GuidanceSource(Base):
    __tablename__ = "guidance_sources"
    __table_args__ = (UniqueConstraint("id", "tenant_id", name="uq_guidance_source_id_tenant"),)
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="guidance")


class GuidanceRelease(Base):
    __tablename__ = "guidance_releases"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_guidance_release_id_tenant"),
        UniqueConstraint("source_id", "version", name="uq_guidance_release_version"),
        ForeignKeyConstraint(["source_id", "tenant_id"], ["guidance_sources.id", "guidance_sources.tenant_id"], name="fk_guidance_release_source_tenant"),
        CheckConstraint("state IN ('draft','approved','active','retired')", name="ck_guidance_release_state"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuidanceChunk(Base):
    __tablename__ = "guidance_chunks"
    __table_args__ = (
        ForeignKeyConstraint(["release_id", "tenant_id"], ["guidance_releases.id", "guidance_releases.tenant_id"], name="fk_guidance_chunk_release_tenant"),
        UniqueConstraint("release_id", "content_hash", name="uq_guidance_chunk_release_hash"),
        CheckConstraint("length(content_hash) = 64", name="ck_guidance_chunk_hash"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    release_id: Mapped[str] = mapped_column(String(128), nullable=False)
    section: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    applicability_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class ReusablePattern(Base):
    __tablename__ = "reusable_patterns"
    __table_args__ = (
        ForeignKeyConstraint(["release_id", "tenant_id"], ["guidance_releases.id", "guidance_releases.tenant_id"], name="fk_pattern_release_tenant"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    release_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
