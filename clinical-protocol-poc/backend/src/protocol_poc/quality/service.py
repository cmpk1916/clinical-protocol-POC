from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.drafting.models import Passage, PassageVersion, SupportLink
from protocol_poc.quality.models import DimensionResult, DimensionStatus, QualityBlocker, QualityScorecard
from protocol_poc.studies.models import Fact
from protocol_poc.tenancy import TenantContext


class QualityService:
    REQUIRED_PASSAGE_SECTIONS = frozenset({
        "synopsis", "objectives_endpoints", "study_design", "eligibility",
    })
    DIMENSIONS = (
        "completeness", "consistency", "traceability", "template_conformance",
        "writer_review_status", "approved_guidance_coverage",
    )

    def __init__(self, session: Session) -> None:
        self.session = session

    def calculate(self, ctx: TenantContext, study_id: str, *, extra_blockers: tuple[QualityBlocker, ...] = ()) -> QualityScorecard:
        passages = list(self.session.scalars(select(Passage).where(Passage.tenant_id == ctx.tenant_id, Passage.study_id == study_id)))
        passage_ids = [item.id for item in passages]
        versions = list(self.session.scalars(select(PassageVersion).where(PassageVersion.tenant_id == ctx.tenant_id, PassageVersion.passage_id.in_(passage_ids), PassageVersion.is_current.is_(True)))) if passage_ids else []
        critical = list(self.session.scalars(select(Fact).where(Fact.tenant_id == ctx.tenant_id, Fact.study_id == study_id, Fact.critical.is_(True), Fact.status.in_(("candidate", "conflicted")))))
        blockers = list(extra_blockers)
        blockers.extend(QualityBlocker("UNRESOLVED_CRITICAL_FACT", "A critical fact requires resolution", fact.id) for fact in critical)
        for passage in passages:
            if passage.status == "stale":
                blockers.append(QualityBlocker("STALE_PASSAGE", "An accepted passage is stale", passage.id))
        for version in versions:
            if version.placeholders:
                blockers.append(QualityBlocker("REQUIRED_PLACEHOLDER", "A required placeholder remains", version.passage_id))
            blockers.extend(
                QualityBlocker(
                    "UNSUPPORTED_CONTENT",
                    finding["message"],
                    version.passage_id,
                )
                for finding in version.validation_findings
                if finding.get("severity") == "blocker"
            )
        if not passages:
            blockers.append(QualityBlocker("VALIDATION_INCOMPLETE", "No scoped passages have completed mandatory validation", study_id))
        sections = [passage.section for passage in passages]
        present_sections = set(sections)
        missing_sections = self.REQUIRED_PASSAGE_SECTIONS - present_sections
        duplicate_sections = {
            section for section in present_sections if sections.count(section) > 1
        }
        blockers.extend(
            QualityBlocker(
                "REQUIRED_SECTION_MISSING",
                f"Required governed section is missing: {section}",
                study_id,
            )
            for section in sorted(missing_sections)
        )
        blockers.extend(
            QualityBlocker(
                "DUPLICATE_SECTION",
                f"More than one governed passage exists for section: {section}",
                study_id,
            )
            for section in sorted(duplicate_sections)
        )
        support_counts: dict[str, int] = {}
        if versions:
            version_ids = [version.id for version in versions]
            for link in self.session.scalars(select(SupportLink).where(SupportLink.tenant_id == ctx.tenant_id, SupportLink.passage_version_id.in_(version_ids))):
                support_counts[link.passage_version_id] = support_counts.get(link.passage_version_id, 0) + 1
        incomplete = [version for version in versions if version.text.strip() and not support_counts.get(version.id) and not version.placeholders]
        blockers.extend(QualityBlocker("INCOMPLETE_PROVENANCE", "A passage lacks support links", version.passage_id) for version in incomplete)

        has_exact_sections = not missing_sections and not duplicate_sections and len(passages) == len(self.REQUIRED_PASSAGE_SECTIONS)
        accepted = sum(item.status == "accepted" for item in passages)
        dimensions = {
            "completeness": self._dimension(
                has_exact_sections,
                len(present_sections & self.REQUIRED_PASSAGE_SECTIONS),
                len(self.REQUIRED_PASSAGE_SECTIONS),
                blockers,
                {"REQUIRED_PLACEHOLDER", "VALIDATION_INCOMPLETE", "REQUIRED_SECTION_MISSING", "DUPLICATE_SECTION"},
            ),
            "consistency": self._dimension(not any(item.code in {"UNSUPPORTED_CONTENT", "CRITICAL_CONTRADICTION", "STALE_PASSAGE"} for item in blockers), 1, 1, blockers, {"UNSUPPORTED_CONTENT", "CRITICAL_CONTRADICTION", "STALE_PASSAGE"}),
            "traceability": self._dimension(not incomplete, len(versions) - len(incomplete), len(versions), blockers, {"INCOMPLETE_PROVENANCE"}),
            "template_conformance": DimensionResult("needs_review" if passages else "not_applicable", 0, 1 if passages else 0),
            "writer_review_status": self._dimension(
                has_exact_sections and accepted == len(self.REQUIRED_PASSAGE_SECTIONS),
                accepted,
                len(self.REQUIRED_PASSAGE_SECTIONS),
                blockers,
                {"STALE_PASSAGE", "REQUIRED_SECTION_MISSING", "DUPLICATE_SECTION"},
            ),
            "approved_guidance_coverage": DimensionResult("needs_review" if passages else "not_applicable", 0, len(passages)),
        }
        return QualityScorecard(dimensions, tuple(blockers), "blocked" if blockers else "eligible")

    @staticmethod
    def _dimension(passed: bool, passed_count: int, applicable_count: int, blockers: list[QualityBlocker], relevant: set[str]) -> DimensionResult:
        codes = tuple(item.code for item in blockers if item.code in relevant)
        status: DimensionStatus = "pass" if passed else ("blocked" if codes else "needs_review")
        return DimensionResult(status, passed_count, applicable_count, codes)
