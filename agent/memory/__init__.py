"""Memory backends for Perseus Memory Agent.

Two implementations of the same MemoryBackend interface:

- ElasticMemoryBackend: Production, cloud-managed, uses Elastic MCP
- EngramMemoryBackend: Self-hosted, MIT-licensed, SQLite-backed

Switching backends requires changing one line of config (MEMORY_BACKEND).
"""

from agent.memory.backend import (
    MemoryBackend,
    MemoryBackendError,
    MemoryEntry,
    MemorySearchResult,
)
from agent.memory.elastic_memory import ElasticMemoryBackend
from agent.memory.engram_memory import EngramMemoryBackend

__all__ = [
    "MemoryBackend",
    "MemoryBackendError",
    "MemoryEntry",
    "MemorySearchResult",
    "ElasticMemoryBackend",
    "EngramMemoryBackend",
]
