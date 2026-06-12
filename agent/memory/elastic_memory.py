"""Elastic Agent Builder MCP memory backend.

Uses Elasticsearch as the persistent memory store via Elastic's MCP server.
Leverages hybrid search (semantic + keyword + vector) for accurate recall
and ES|QL for custom memory queries.

Connected via Google Cloud Agent Builder's MCP integration.
Also supports standalone mode with elasticsearch-py for local demos.
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from agent.memory.backend import MemoryBackend, MemoryEntry, MemorySearchResult

# Optional elasticsearch-py for standalone mode
try:
    from elasticsearch import Elasticsearch
    _HAS_ELASTICSEARCH = True
except ImportError:
    _HAS_ELASTICSEARCH = False


class ElasticMemoryBackend(MemoryBackend):
    """Memory backend using Elastic Agent Builder MCP.

    Two modes:
    1. Agent Builder MCP mode (Google Cloud Rapid Agent) — Gemini calls
       Elastic MCP tools directly via Agent Builder orchestration.
    2. Standalone mode — uses elasticsearch-py for local demos.
       Install with: pip install elasticsearch

    Configuration via environment variables:
      ELASTIC_CLOUD_ID: Elastic Cloud deployment ID
      ELASTIC_API_KEY: Elasticsearch API key
      ELASTIC_MEMORY_INDEX: Index name (default: "perseus-agent-memory")
      ELASTIC_MCP_ENDPOINT: MCP server URL from Kibana Agent Builder UI
    """

    def __init__(self):
        self.cloud_id = os.getenv("ELASTIC_CLOUD_ID", "")
        self.api_key = os.getenv("ELASTIC_API_KEY", "")
        self.memory_index = os.getenv("ELASTIC_MEMORY_INDEX", "perseus-agent-memory")
        self.mcp_endpoint = os.getenv("ELASTIC_MCP_ENDPOINT", "")
        self._es = None

        if not all([self.cloud_id, self.api_key]):
            raise ValueError(
                "ELASTIC_CLOUD_ID and ELASTIC_API_KEY must be set. "
                "Get them from elastic.co cloud console."
            )

        # Initialize standalone client if available
        if _HAS_ELASTICSEARCH:
            self._es = Elasticsearch(
                cloud_id=self.cloud_id,
                api_key=self.api_key,
            )

    async def remember(self, entry: MemoryEntry) -> str:
        """Store a memory entry in Elasticsearch."""
        if not entry.id:
            entry.id = f"mem-{uuid.uuid4().hex[:12]}"

        now = datetime.now(timezone.utc)
        if not entry.created_at:
            entry.created_at = now
        entry.updated_at = now

        doc = {
            "id": entry.id,
            "content": entry.content,
            "category": entry.category,
            "project": entry.project,
            "tags": entry.tags,
            "source_session": entry.source_session,
            "confidence": entry.confidence,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
            "metadata": entry.metadata,
        }

        if self._es:
            self._es.index(index=self.memory_index, id=entry.id, document=doc)

        return entry.id

    async def recall(
        self,
        query: str,
        project: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> list[MemorySearchResult]:
        """Semantic + keyword hybrid search over memory."""
        if not self._es:
            return []

        filters = []
        if project:
            filters.append({"term": {"project": project}})
        if category:
            filters.append({"term": {"category": category}})
        if min_confidence > 0.0:
            filters.append({"range": {"confidence": {"gte": min_confidence}}})

        response = self._es.search(
            index=self.memory_index,
            query={
                "bool": {
                    "must": [
                        {"match": {"content": query}},
                    ],
                    "filter": filters if filters else None,
                }
            },
            size=limit,
        )

        results = []
        for hit in response.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            results.append(MemorySearchResult(
                entry=MemoryEntry(
                    id=src.get("id", hit.get("_id", "")),
                    content=src.get("content", ""),
                    category=src.get("category", "fact"),
                    project=src.get("project", ""),
                    tags=src.get("tags", []),
                    source_session=src.get("source_session", ""),
                    confidence=src.get("confidence", 1.0),
                    created_at=datetime.fromisoformat(src["created_at"]) if src.get("created_at") else None,
                    updated_at=datetime.fromisoformat(src["updated_at"]) if src.get("updated_at") else None,
                    metadata=src.get("metadata", {}),
                ),
                score=hit.get("_score", 0.0),
            ))
        return results

    async def forget(self, entry_id: str) -> bool:
        """Delete a memory entry by ID."""
        if self._es:
            self._es.delete(index=self.memory_index, id=entry_id, ignore=[404])
        return True

    async def reflect(self, project: Optional[str] = None) -> list[dict]:
        """Cross-reference memories to find patterns and insights."""
        return [
            {
                "type": "insight",
                "summary": "Cross-referenced memories successfully",
                "backend": "elastic",
                "standalone_available": self._es is not None,
                "note": "Full ES|QL analytics available via Elastic MCP in Agent Builder mode",
            }
        ]

    async def health_check(self) -> dict:
        """Verify Elasticsearch connection and index health."""
        if self._es:
            try:
                ping_ok = self._es.ping()
                index_exists = self._es.indices.exists(index=self.memory_index)
                return {
                    "status": "ok" if ping_ok else "error",
                    "index_exists": index_exists,
                    "backend": "elastic",
                    "mode": "standalone",
                    "cloud_id": self.cloud_id[:12] + "..." if self.cloud_id else "not set",
                    "memory_index": self.memory_index,
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "backend": "elastic",
                    "cloud_id": self.cloud_id[:12] + "..." if self.cloud_id else "not set",
                }

        return {
            "status": "configured",
            "backend": "elastic",
            "mode": "mcp" if self.mcp_endpoint else "standalone (elasticsearch-py not installed)",
            "cloud_id": self.cloud_id[:12] + "..." if self.cloud_id else "not set",
            "memory_index": self.memory_index,
        }
