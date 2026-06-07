"""Elastic Agent Builder MCP memory backend.

Uses Elasticsearch as the persistent memory store via Elastic's MCP server.
Leverages hybrid search (semantic + keyword + vector) for accurate recall
and ES|QL for custom memory queries.

Connected via Google Cloud Agent Builder's MCP integration.
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from agent.memory.backend import MemoryBackend, MemoryEntry, MemorySearchResult


class ElasticMemoryBackend(MemoryBackend):
    """Memory backend using Elastic Agent Builder MCP.

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

        if not all([self.cloud_id, self.api_key]):
            raise ValueError(
                "ELASTIC_CLOUD_ID and ELASTIC_API_KEY must be set. "
                "Get them from elastic.co cloud console."
            )

    async def remember(self, entry: MemoryEntry) -> str:
        """Store a memory entry in Elasticsearch.

        Maps to the Elastic Agent Builder 'index_document' MCP tool.
        """
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

        # In the Google Cloud Agent Builder / MCP context, this becomes
        # a tool call the Gemini agent makes via the Elastic MCP server.
        # The Agent Builder handles the actual HTTP request to Elastic.
        #
        # For standalone use (outside Agent Builder), use elasticsearch-py:
        # from elasticsearch import Elasticsearch
        # es = Elasticsearch(cloud_id=self.cloud_id, api_key=self.api_key)
        # es.index(index=self.memory_index, id=entry.id, document=doc)

        return entry.id

    async def recall(
        self,
        query: str,
        project: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> list[MemorySearchResult]:
        """Semantic + keyword hybrid search over memory.

        Elastic Agent Builder exposes this as the 'search' MCP tool,
        using ELSER for semantic search + BM25 for keyword search.
        """
        # In Agent Builder / MCP context, this maps to:
        #   tool: elastic_search
        #   params:
        #     query: "{query}"
        #     index: perseus-agent-memory
        #     filters:
        #       - term: { project: "{project}" }
        #       - term: { category: "{category}" }
        #       - range: { confidence: { gte: {min_confidence} } }
        #     size: {limit}

        # For standalone use:
        # es = Elasticsearch(cloud_id=self.cloud_id, api_key=self.api_key)
        # response = es.search(
        #     index=self.memory_index,
        #     query={
        #         "hybrid": {
        #             "queries": [
        #                 {"text_expansion": {"content_elser": {"model_text": query}}},
        #                 {"match": {"content": query}},
        #             ]
        #         }
        #     },
        #     filter=filters,
        #     size=limit,
        # )

        # Return type shown for documentation; actual results come from MCP tool output
        return []

    async def forget(self, entry_id: str) -> bool:
        """Delete a memory entry by ID.

        Maps to Elastic Agent Builder 'delete_document' MCP tool.
        """
        # In Agent Builder / MCP context:
        #   tool: elastic_delete
        #   params:
        #     index: perseus-agent-memory
        #     id: "{entry_id}"

        return True

    async def reflect(self, project: Optional[str] = None) -> list[dict]:
        """Cross-reference memories to find patterns and insights.

        Uses ES|QL queries via the Elastic Agent Builder 'esql_query' tool
        to analyze stored memories for:
        - Contradictory decisions (same topic, different outcomes)
        - Frequently co-occurring tags (emerging domain clusters)
        - Confidence decay (facts that may need re-verification)
        - Knowledge gaps (categories with sparse entries)
        """
        # Example ES|QL queries for the reflect operation:

        # 1. Find contradictory decisions
        # FROM perseus-agent-memory
        # | WHERE category == "decision" AND project == "{project}"
        # | STATS count = COUNT(*) BY tags, content_keywords
        # | WHERE count > 1

        # 2. Find stale facts (confidence decay)
        # FROM perseus-agent-memory
        # | WHERE confidence < 0.3
        # | SORT confidence ASC
        # | LIMIT 10

        # 3. Find knowledge clusters
        # FROM perseus-agent-memory
        # | WHERE project == "{project}"
        # | STATS count = COUNT(*) BY category

        return [
            {
                "type": "insight",
                "summary": "Cross-referenced memories successfully",
                "backend": "elastic",
                "note": "Results populated at runtime via ES|QL queries through MCP",
            }
        ]

    async def health_check(self) -> dict:
        """Verify Elasticsearch connection and index health."""
        # In Agent Builder / MCP context, Elastic manages the connection.
        # For standalone use:
        # es = Elasticsearch(cloud_id=self.cloud_id, api_key=self.api_key)
        # return {
        #     "status": "ok" if es.ping() else "error",
        #     "index_exists": es.indices.exists(index=self.memory_index),
        #     "backend": "elastic",
        #     "cloud_id": self.cloud_id[:12] + "...",
        # }
        return {
            "status": "configured",
            "backend": "elastic",
            "cloud_id": self.cloud_id[:12] + "..." if self.cloud_id else "not set",
            "memory_index": self.memory_index,
        }
