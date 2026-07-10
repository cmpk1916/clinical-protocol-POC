from enum import StrEnum


class TaskType(StrEnum):
    EXTRACT_FACTS = "extract_facts"
    RETRIEVE_GUIDANCE = "retrieve_guidance"
    DRAFT_PASSAGE = "draft_passage"
    MAP_CLAIMS = "map_claims"
    SEMANTIC_REVIEW = "semantic_review"
    EXPLAIN_FINDING = "explain_finding"
