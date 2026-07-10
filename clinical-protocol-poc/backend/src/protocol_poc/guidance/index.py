from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class GuidanceDocument:
    chunk_id: str
    release_id: str
    tenant_id: str | None
    content: str
    content_hash: str


class GuidanceIndex:
    """A rebuildable SQLite FTS projection; relational releases remain authoritative."""

    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute(
            "CREATE VIRTUAL TABLE guidance_fts USING fts5(chunk_id UNINDEXED, release_id UNINDEXED, tenant_id UNINDEXED, content, content_hash UNINDEXED)"
        )

    def rebuild(self, documents: list[GuidanceDocument]) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM guidance_fts")
            self.connection.executemany(
                "INSERT INTO guidance_fts(chunk_id, release_id, tenant_id, content, content_hash) VALUES (?, ?, ?, ?, ?)",
                [(item.chunk_id, item.release_id, item.tenant_id or "", item.content, item.content_hash) for item in documents],
            )

    def search(self, query: str, *, tenant_id: str) -> list[GuidanceDocument]:
        normalized = " ".join(token for token in query.replace('"', " ").split() if token)
        if not normalized:
            return []
        rows = self.connection.execute(
            "SELECT chunk_id, release_id, tenant_id, content, content_hash FROM guidance_fts WHERE guidance_fts MATCH ? AND tenant_id IN ('', ?) ORDER BY bm25(guidance_fts), chunk_id",
            (normalized, tenant_id),
        ).fetchall()
        return [GuidanceDocument(row[0], row[1], row[2] or None, row[3], row[4]) for row in rows]
