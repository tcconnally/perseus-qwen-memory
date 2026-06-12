"""Tests for the direct-SQLite Engram backend — real database, tmp file."""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.memory.backend import MemoryEntry  # noqa: E402
from agent.memory.engram_memory import EngramMemoryBackend  # noqa: E402


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGRAM_DB_PATH", str(tmp_path / "engram-test.db"))
    return EngramMemoryBackend()


def test_remember_recall_roundtrip(backend):
    eid = asyncio.run(backend.remember(MemoryEntry(
        content="We use pgvector for vector search",
        category="fact", project="demo", tags=["vector-db"],
        confidence=0.9,
    )))

    results = asyncio.run(backend.recall("pgvector", project="demo"))
    assert len(results) == 1
    entry = results[0].entry
    assert entry.id == eid
    assert entry.content == "We use pgvector for vector search"
    assert entry.tags == ["vector-db"]
    assert entry.confidence == 0.9
    assert entry.created_at is not None  # decay needs real timestamps


def test_remember_upserts_by_id_for_confidence_writeback(backend):
    entry = MemoryEntry(content="old fact text", category="fact",
                        project="demo", id="mem-fixed", confidence=0.9)
    asyncio.run(backend.remember(entry))

    entry.confidence = 0.2  # decay write-back path
    asyncio.run(backend.remember(entry))

    results = asyncio.run(backend.recall("fact text", project="demo"))
    assert len(results) == 1
    assert results[0].entry.confidence == 0.2


def test_min_confidence_floor_filters(backend):
    asyncio.run(backend.remember(MemoryEntry(
        content="nearly forgotten fact", category="fact",
        project="demo", confidence=0.2,
    )))
    assert asyncio.run(backend.recall("forgotten", project="demo",
                                      min_confidence=0.3)) == []
    assert len(asyncio.run(backend.recall("forgotten", project="demo"))) == 1


def test_forget_soft_invalidates(backend):
    eid = asyncio.run(backend.remember(MemoryEntry(
        content="temporary fact", category="fact", project="demo",
    )))
    assert asyncio.run(backend.forget(eid)) is True
    assert asyncio.run(backend.recall("temporary", project="demo")) == []
    assert asyncio.run(backend.forget(eid)) is False  # already gone


def test_project_isolation(backend):
    asyncio.run(backend.remember(MemoryEntry(
        content="alpha secret", category="fact", project="alpha",
    )))
    assert asyncio.run(backend.recall("secret", project="beta")) == []
    assert len(asyncio.run(backend.recall("secret", project="alpha"))) == 1


def test_wildcard_query_returns_everything_in_scope(backend):
    for i in range(3):
        asyncio.run(backend.remember(MemoryEntry(
            content=f"fact number {i}", category="fact", project="demo",
        )))
    assert len(asyncio.run(backend.recall("*", project="demo"))) == 3


def test_fts_operators_in_query_are_inert(backend):
    asyncio.run(backend.remember(MemoryEntry(
        content="plain stored fact", category="fact", project="demo",
    )))
    # NEAR/AND/quotes would be FTS5 syntax errors if unescaped.
    results = asyncio.run(
        backend.recall('fact" OR NEAR(x y, 1) AND "', project="demo")
    )
    assert isinstance(results, list)  # no sqlite3.OperationalError


def test_reflect_surfaces_stale_facts(backend):
    asyncio.run(backend.remember(MemoryEntry(
        content="stale old belief", category="fact", project="demo",
        confidence=0.1,
    )))
    insights = asyncio.run(backend.reflect(project="demo"))
    assert any(i["type"] == "stale_fact" for i in insights)


def test_health_check_reports_counts(backend):
    asyncio.run(backend.remember(MemoryEntry(
        content="x", category="fact", project="demo",
    )))
    health = asyncio.run(backend.health_check())
    assert health["status"] == "ok"
    assert health["entry_count"] == 1
