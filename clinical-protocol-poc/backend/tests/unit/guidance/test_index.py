from protocol_poc.guidance.index import GuidanceDocument, GuidanceIndex


def test_index_returns_matching_active_documents_with_provenance() -> None:
    index = GuidanceIndex()
    index.rebuild([
        GuidanceDocument("chunk-a", "release-a", None, "Eligibility criteria should be precise", "hash-a"),
        GuidanceDocument("chunk-b", "release-b", None, "Describe study objectives", "hash-b"),
    ])

    results = index.search("eligibility", tenant_id="tenant-a")

    assert [result.chunk_id for result in results] == ["chunk-a"]
    assert results[0].release_id == "release-a"


def test_sponsor_pattern_cannot_cross_tenant() -> None:
    index = GuidanceIndex()
    index.rebuild([
        GuidanceDocument("pattern-a", "release-a", "tenant-a", "Randomized sponsor pattern", "hash-a")
    ])

    assert index.search("randomized", tenant_id="tenant-b") == []
