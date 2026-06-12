"""Engram-rs memory backend — self-hosted, MIT-licensed persistent memory.

Talks directly to the Engram-rs SQLite database (same `facts` schema that
`engram serve` v0.5.x uses), so memories written by the agent are visible
to engram's MCP/REST interface and vice versa.

Why direct DB access instead of the MCP surface:
- zero dependencies (stdlib sqlite3) and no subprocess lifecycle
- deterministic id-based writes (engram's `memory_add` tool runs LLM
  fact extraction — non-deterministic, and it needs an LLM provider)
- confidence write-back for decay, which the MCP tools don't expose

Configuration via environment variables:
  ENGRAM_DATA_DIR: Data directory (default: "~/.hermes/mnemosyne/data")
  ENGRAM_DB_PATH: Full path to the SQLite db (overrides ENGRAM_DATA_DIR)

Engram-rs: https://github.com/tcconnally/engram-rs (MIT licensed)
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from agent.memory.backend import (
    MemoryBackend,
    MemoryBackendError,
    MemoryEntry,
    MemorySearchResult,
)

# Mirrors engram-rs v0.5.x — kept in sync so either side can create the db.
_FACTS_DDL = """
CREATE TABLE IF NOT EXISTS facts (
    id              TEXT PRIMARY KEY,
    text            TEXT NOT NULL,
    org_id          TEXT NOT NULL DEFAULT 'default',
    agent_id        TEXT,
    user_id         TEXT,
    session_id      TEXT,
    tier            TEXT NOT NULL DEFAULT 'conversation',
    category        TEXT,
    source          TEXT,
    confidence      REAL,
    valid_from      TEXT NOT NULL,
    invalid_at      TEXT,
    created_at      TEXT NOT NULL,
    entity_refs     TEXT NOT NULL DEFAULT '[]',
    supersedes      TEXT,
    superseded_by   TEXT,
    access_count    INTEGER NOT NULL DEFAULT 0,
    last_accessed   TEXT,
    metadata        TEXT NOT NULL DEFAULT 'null'
)
"""

_FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts "
    "USING fts5(fact_id UNINDEXED, text)"
)


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _fts_query(query: str) -> str:
    """Quote each term so user input can't inject FTS5 operators."""
    terms = [
        '"{}"'.format(w.replace('"', '""'))
        for w in query.split()
        if w.strip('"')
    ]
    return " OR ".join(terms)


class EngramMemoryBackend(MemoryBackend):
    """Self-hosted memory backend over the Engram-rs SQLite store."""

    SOURCE = "perseus-qwen-agent"

    def __init__(self):
        data_dir = os.getenv(
            "ENGRAM_DATA_DIR",
            os.path.expanduser("~/.hermes/mnemosyne/data"),
        )
        self.db_path = os.getenv(
            "ENGRAM_DB_PATH",
            os.path.join(data_dir, "mnemosyne.db"),
        )
        self._conn: Optional[sqlite3.Connection] = None

    # ── connection ──────────────────────────────────────────────────

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            try:
                os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(_FACTS_DDL)
                conn.execute(_FTS_DDL)
                conn.commit()
                self._conn = conn
            except sqlite3.Error as exc:
                raise MemoryBackendError(
                    f"Engram database unavailable at {self.db_path}: {exc}"
                ) from exc
        return self._conn

    # ── MemoryBackend interface ─────────────────────────────────────

    async def remember(self, entry: MemoryEntry) -> str:
        """Store (or update by id) a memory entry in the facts table."""
        if not entry.id:
            entry.id = f"mem-{uuid.uuid4().hex[:12]}"

        now = datetime.now(timezone.utc)
        entry.created_at = entry.created_at or now
        entry.updated_at = now

        meta = json.dumps({
            "tags": entry.tags,
            "project": entry.project,
            "extra": entry.metadata,
        })

        try:
            db = self._db()
            with db:
                db.execute(
                    """
                    INSERT INTO facts
                        (id, text, user_id, session_id, category, source,
                         confidence, valid_from, created_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        text = excluded.text,
                        category = excluded.category,
                        confidence = excluded.confidence,
                        metadata = excluded.metadata,
                        invalid_at = NULL
                    """,
                    (
                        entry.id,
                        entry.content,
                        entry.project,
                        entry.source_session,
                        entry.category,
                        self.SOURCE,
                        entry.confidence,
                        entry.created_at.isoformat(),
                        entry.created_at.isoformat(),
                        meta,
                    ),
                )
                db.execute("DELETE FROM facts_fts WHERE fact_id = ?", (entry.id,))
                db.execute(
                    "INSERT INTO facts_fts (fact_id, text) VALUES (?, ?)",
                    (entry.id, entry.content),
                )
        except sqlite3.Error as exc:
            raise MemoryBackendError(f"Engram store failed: {exc}") from exc

        return entry.id

    async def recall(
        self,
        query: str,
        project: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> list[MemorySearchResult]:
        """FTS5 search over live (non-invalidated) facts.

        Returns [] only when the search succeeded and found nothing;
        database failures raise MemoryBackendError.
        """
        filters = ["f.invalid_at IS NULL", "f.superseded_by IS NULL"]
        params: list = []
        if project:
            filters.append("f.user_id = ?")
            params.append(project)
        if category:
            filters.append("f.category = ?")
            params.append(category)
        if min_confidence > 0.0:
            filters.append("f.confidence >= ?")
            params.append(min_confidence)

        try:
            db = self._db()
            if not query or query == "*":
                sql = (
                    "SELECT f.*, 0.0 AS rank FROM facts f "
                    f"WHERE {' AND '.join(filters)} "
                    "ORDER BY f.created_at DESC LIMIT ?"
                )
                rows = db.execute(sql, (*params, limit)).fetchall()
            else:
                match = _fts_query(query)
                if not match:
                    return []
                sql = (
                    "SELECT f.*, bm25(facts_fts) AS rank "
                    "FROM facts_fts JOIN facts f ON f.id = facts_fts.fact_id "
                    f"WHERE facts_fts MATCH ? AND {' AND '.join(filters)} "
                    "ORDER BY rank LIMIT ?"
                )
                rows = db.execute(sql, (match, *params, limit)).fetchall()
        except sqlite3.Error as exc:
            raise MemoryBackendError(f"Engram search failed: {exc}") from exc

        results = []
        for row in rows:
            try:
                meta = json.loads(row["metadata"] or "null") or {}
            except (json.JSONDecodeError, TypeError):
                meta = {}
            entry = MemoryEntry(
                id=row["id"],
                content=row["text"],
                category=row["category"] or "fact",
                project=row["user_id"] or meta.get("project", ""),
                tags=meta.get("tags") or [],
                source_session=row["session_id"],
                confidence=row["confidence"] if row["confidence"] is not None else 1.0,
                created_at=_parse_dt(row["created_at"]),
                updated_at=_parse_dt(row["last_accessed"]) or _parse_dt(row["created_at"]),
                metadata=meta.get("extra") or {},
            )
            # bm25 rank: lower is better; negate so higher score = better.
            results.append(
                MemorySearchResult(
                    entry=entry,
                    score=-float(row["rank"]),
                    search_method="fts5",
                )
            )
        return results

    async def forget(self, entry_id: str) -> bool:
        """Soft-invalidate a fact (engram semantics: invalid_at, not DELETE)."""
        try:
            db = self._db()
            with db:
                cur = db.execute(
                    "UPDATE facts SET invalid_at = ? "
                    "WHERE id = ? AND invalid_at IS NULL",
                    (datetime.now(timezone.utc).isoformat(), entry_id),
                )
                db.execute("DELETE FROM facts_fts WHERE fact_id = ?", (entry_id,))
            return cur.rowcount > 0
        except sqlite3.Error as exc:
            raise MemoryBackendError(f"Engram forget failed: {exc}") from exc

    async def reflect(self, project: Optional[str] = None) -> list[dict]:
        """Surface patterns: stale facts and category distribution."""
        where = "invalid_at IS NULL"
        params: list = []
        if project:
            where += " AND user_id = ?"
            params.append(project)

        try:
            db = self._db()
            insights: list[dict] = []
            stale = db.execute(
                f"SELECT id, text, confidence FROM facts "
                f"WHERE {where} AND confidence < 0.3 "
                "ORDER BY confidence ASC LIMIT 10",
                params,
            ).fetchall()
            for row in stale:
                insights.append({
                    "type": "stale_fact",
                    "summary": (
                        "Low-confidence memory may need re-verification: "
                        f"{row['text'][:120]}"
                    ),
                    "confidence": row["confidence"],
                    "id": row["id"],
                    "backend": "engram-rs",
                })
            dist = db.execute(
                f"SELECT category, COUNT(*) AS n FROM facts "
                f"WHERE {where} GROUP BY category ORDER BY n DESC",
                params,
            ).fetchall()
            if dist:
                pretty = ", ".join(
                    f"{row['category'] or 'uncategorized'}: {row['n']}" for row in dist
                )
                insights.append({
                    "type": "knowledge_distribution",
                    "summary": f"Knowledge by category — {pretty}",
                    "backend": "engram-rs",
                })
            return insights
        except sqlite3.Error as exc:
            raise MemoryBackendError(f"Engram reflect failed: {exc}") from exc

    async def health_check(self) -> dict:
        """Verify the database is reachable. Never raises."""
        try:
            db = self._db()
            count = db.execute(
                "SELECT COUNT(*) FROM facts WHERE invalid_at IS NULL"
            ).fetchone()[0]
            size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            return {
                "status": "ok",
                "backend": "engram-rs",
                "db_path": self.db_path,
                "entry_count": count,
                "db_size_bytes": size,
            }
        except (MemoryBackendError, sqlite3.Error, OSError) as exc:
            return {
                "status": "error",
                "backend": "engram-rs",
                "db_path": self.db_path,
                "error": str(exc),
            }
