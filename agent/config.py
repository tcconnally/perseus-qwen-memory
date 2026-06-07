"""Agent configuration — single source of truth.

Switch backends by changing MEMORY_BACKEND:
  - "elastic" → Elastic Cloud (managed)
  - "engram"  → Engram-rs (self-hosted, MIT)

Switch LLM by changing LLM_PROVIDER:
  - "qwen"  → Qwen Cloud (via DashScope OpenAI-compatible API)
  - "others" → Any OpenAI-compatible endpoint

Everything else in the agent is backend-agnostic.
"""

import os
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Configuration for the Perseus Memory Agent."""

    # ── LLM Provider ──────────────────────────────────────────────
    llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "qwen")
    )
    llm_api_key: str = field(
        default_factory=lambda: os.getenv("DASHSCOPE_API_KEY", "")
    )
    llm_base_url: str = field(
        default_factory=lambda: os.getenv(
            "LLM_BASE_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "qwen-max")
    )

    # ── Memory backend selection ──────────────────────────────────
    memory_backend: str = field(
        default_factory=lambda: os.getenv("MEMORY_BACKEND", "engram")
    )

    # Elastic Cloud (when MEMORY_BACKEND=elastic)
    elastic_cloud_id: str = field(
        default_factory=lambda: os.getenv("ELASTIC_CLOUD_ID", "")
    )
    elastic_api_key: str = field(
        default_factory=lambda: os.getenv("ELASTIC_API_KEY", "")
    )
    elastic_memory_index: str = field(
        default_factory=lambda: os.getenv(
            "ELASTIC_MEMORY_INDEX", "perseus-agent-memory"
        )
    )

    # Engram-rs (when MEMORY_BACKEND=engram)
    engram_bin: str = field(
        default_factory=lambda: os.getenv("ENGRAM_BIN", "engram")
    )
    engram_db_path: str = field(
        default_factory=lambda: os.getenv(
            "ENGRAM_DB_PATH",
            os.path.expanduser("~/.hermes/mnemosyne/data/mnemosyne.db"),
        )
    )

    # ── Agent behavior ────────────────────────────────────────────
    max_context_tokens: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONTEXT_TOKENS", "32000"))
    )
    recall_count: int = field(
        default_factory=lambda: int(os.getenv("RECALL_COUNT", "10"))
    )
    auto_reflect: bool = field(
        default_factory=lambda: os.getenv("AUTO_REFLECT", "true").lower() == "true"
    )
    confidence_decay_rate: float = field(
        default_factory=lambda: float(os.getenv("CONFIDENCE_DECAY_RATE", "0.05"))
    )

    def validate(self) -> list[str]:
        """Validate configuration. Returns list of issues (empty = valid)."""
        issues = []

        if self.memory_backend not in ("elastic", "engram"):
            issues.append(f"Invalid MEMORY_BACKEND: {self.memory_backend}")

        if self.memory_backend == "elastic":
            if not self.elastic_cloud_id:
                issues.append("ELASTIC_CLOUD_ID is required for elastic backend")
            if not self.elastic_api_key:
                issues.append("ELASTIC_API_KEY is required for elastic backend")

        if not self.llm_api_key:
            issues.append(
                "DASHSCOPE_API_KEY is required. "
                "Get one at: https://bailian.console.aliyun.com/"
            )

        return issues
