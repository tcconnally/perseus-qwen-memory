"""Tests for decay write-back, contradiction supersede, context budget,
and LLM error handling.

Everything runs against an in-memory backend stub and a stubbed LLM —
no engram binary, no DashScope key, no Elastic deployment.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.config import AgentConfig  # noqa: E402
from agent.main import LLMError, MemoryManager, PerseusQwenAgent  # noqa: E402
from agent.memory.backend import (  # noqa: E402
    MemoryBackend,
    MemoryEntry,
    MemorySearchResult,
)


class StubBackend(MemoryBackend):
    """In-memory MemoryBackend: token-overlap recall, id-upsert remember."""

    def __init__(self):
        self.entries: dict[str, MemoryEntry] = {}

    async def remember(self, entry: MemoryEntry) -> str:
        if not entry.id:
            entry.id = f"mem-{len(self.entries)}"
        self.entries[entry.id] = entry
        return entry.id

    async def recall(self, query, project=None, category=None, limit=10,
                     min_confidence=0.0):
        q_tokens = set(query.lower().split())
        results = []
        for e in self.entries.values():
            if project and e.project != project:
                continue
            if category and e.category != category:
                continue
            if e.confidence < min_confidence:
                continue
            overlap = len(q_tokens & set(e.content.lower().split()))
            if query in ("", "*") or overlap:
                results.append(
                    MemorySearchResult(entry=e, score=float(overlap),
                                       search_method="stub")
                )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def forget(self, entry_id: str) -> bool:
        return self.entries.pop(entry_id, None) is not None

    async def reflect(self, project=None):
        return []

    async def health_check(self):
        return {"status": "ok", "backend": "stub"}


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("MEMORY_BACKEND", "engram")
    return AgentConfig()


@pytest.fixture
def manager(config):
    return MemoryManager(StubBackend(), config)


# ── MemoryEntry regression ──────────────────────────────────────────────────


def test_memory_entry_constructs_without_id():
    assert MemoryEntry(content="x", category="fact", project="p").id == ""


# ── store defaults ──────────────────────────────────────────────────────────


def test_store_defaults_to_decayable_confidence(manager):
    eid = asyncio.run(manager.store("we use redis", "fact", "p"))
    assert manager.memory.entries[eid].confidence == 0.9


# ── decay write-back ────────────────────────────────────────────────────────


def _aged_entry(backend, content, confidence, days_old, project="p"):
    entry = MemoryEntry(
        content=content, category="fact", project=project,
        id=f"mem-{content[:8]}", confidence=confidence,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_old),
        updated_at=datetime.now(timezone.utc) - timedelta(days=days_old),
    )
    backend.entries[entry.id] = entry
    return entry


def _agent_with(backend, config):
    agent = PerseusQwenAgent.__new__(PerseusQwenAgent)  # skip __init__ (no LLM)
    agent.config = config
    agent.memory_backend = backend
    agent.memory_mgr = MemoryManager(backend, config)
    agent.current_project = "p"
    agent.session_id = "s"
    return agent


def test_decay_is_written_back(config):
    backend = StubBackend()
    old = _aged_entry(backend, "we use p redis cache", 0.9, days_old=10)
    agent = _agent_with(backend, config)

    decayed = asyncio.run(agent._decay_confidence())

    assert len(decayed) == 1
    # 0.9 - 0.05*10 = 0.4, and the stored entry actually changed:
    assert backend.entries[old.id].confidence == pytest.approx(0.4)
    assert decayed[0]["forgotten"] is False


def test_decay_below_floor_marks_forgotten(config):
    backend = StubBackend()
    _aged_entry(backend, "we use p ancient fact", 0.9, days_old=14)
    agent = _agent_with(backend, config)

    decayed = asyncio.run(agent._decay_confidence())
    assert decayed[0]["forgotten"] is True  # 0.9 - 0.7 = 0.2 < 0.3


def test_pinned_full_confidence_does_not_decay(config):
    backend = StubBackend()
    pinned = _aged_entry(backend, "we use p verified fact", 1.0, days_old=30)
    agent = _agent_with(backend, config)

    decayed = asyncio.run(agent._decay_confidence())
    assert decayed == []
    assert backend.entries[pinned.id].confidence == 1.0


def test_fresh_memories_do_not_decay(config):
    backend = StubBackend()
    fresh = _aged_entry(backend, "we use p new fact", 0.9, days_old=0)
    agent = _agent_with(backend, config)

    assert asyncio.run(agent._decay_confidence()) == []
    assert backend.entries[fresh.id].confidence == 0.9


# ── contradiction supersede ─────────────────────────────────────────────────


def test_supersede_demotes_contradicted_fact(manager):
    backend = manager.memory
    old = _aged_entry(
        backend, "We use Pinecone for vector search", 0.9, days_old=7
    )

    result = asyncio.run(
        manager.supersede("p", "We switched to pgvector for vector search")
    )

    assert len(result["superseded"]) == 1
    assert result["superseded"][0]["id"] == old.id
    assert result["superseded"][0]["old_confidence"] == 0.9
    # Old fact demoted below the recall floor; new fact stored at 0.9.
    assert backend.entries[old.id].confidence == 0.2
    assert backend.entries[result["id"]].confidence == 0.9


def test_supersede_ignores_unrelated_facts(manager):
    backend = manager.memory
    unrelated = _aged_entry(
        backend, "Pytest runs the whole suite under coverage", 0.9, days_old=7
    )

    result = asyncio.run(
        manager.supersede("p", "We switched to pgvector for vector search")
    )
    assert result["superseded"] == []
    assert backend.entries[unrelated.id].confidence == 0.9


def test_supersede_ignores_identical_restatement(manager):
    backend = manager.memory
    same = _aged_entry(
        backend, "We use pgvector for vector search", 0.9, days_old=7
    )
    result = asyncio.run(
        manager.supersede("p", "We use pgvector for vector search")
    )
    assert result["superseded"] == []
    assert backend.entries[same.id].confidence == 0.9


# ── context budget ──────────────────────────────────────────────────────────


def test_recall_context_respects_budget(monkeypatch, config):
    config.max_context_chars = 300
    backend = StubBackend()
    manager = MemoryManager(backend, config)
    for i in range(10):
        entry = MemoryEntry(
            content=f"budget fact number {i} " + "x" * 80,
            category="fact", project="p", id=f"mem-{i}",
            confidence=0.5 + i * 0.05,
        )
        backend.entries[entry.id] = entry

    context = asyncio.run(manager.recall_context("p", "budget fact"))

    assert len(context) <= 300 + 120  # budget + truncation note
    assert "showing top" in context
    # Highest-confidence memory survived the cut; lowest did not.
    assert "number 9" in context
    assert "number 0" not in context


def test_recall_context_no_note_when_under_budget(config):
    backend = StubBackend()
    manager = MemoryManager(backend, config)
    backend.entries["m"] = MemoryEntry(
        content="short fact", category="fact", project="p", id="m",
        confidence=0.9,
    )
    context = asyncio.run(manager.recall_context("p", "short fact"))
    assert "showing top" not in context


# ── LLM error handling ──────────────────────────────────────────────────────


class _FailingLLM:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    async def chat(self, messages, **kwargs):
        self.calls += 1
        raise self.error


def test_process_message_returns_clean_error_and_stores_nothing(config):
    backend = StubBackend()
    agent = _agent_with(backend, config)
    agent.llm = _FailingLLM(LLMError("HTTP 429: rate limited", status=429,
                                     retryable=True))

    reply = asyncio.run(agent.process_message("what database do we use?"))

    assert "couldn't reach the language model" in reply
    assert "[LLM Error" not in reply
    # Nothing persisted — not the interaction, not extracted "facts".
    assert backend.entries == {}


def test_auto_store_skips_extraction_on_llm_error(config):
    backend = StubBackend()
    agent = _agent_with(backend, config)
    agent.llm = _FailingLLM(LLMError("boom", retryable=False))

    asyncio.run(agent._auto_store("user msg", "assistant reply"))

    # The interaction context entry is stored, but no extracted facts —
    # and crucially, no "[LLM Error...]" content anywhere.
    contents = [e.content for e in backend.entries.values()]
    assert len(contents) == 1
    assert contents[0].startswith("User asked:")
    assert not any("LLM" in c and "Error" in c for c in contents)


def test_llm_error_is_typed_not_stringly(config):
    err = LLMError("HTTP 400: bad request", status=400, retryable=False)
    assert err.status == 400
    assert err.retryable is False
