"""Perseus Qwen Memory Agent — main agent loop.

A Qwen Cloud-powered agent with persistent, evolving memory that compounds
knowledge across sessions. Built for the Qwen Cloud Hackathon 2026
MemoryAgent Track: "Build an Agent with persistent memory that autonomously
accumulates experience, remembers user preferences, and makes increasingly
accurate decisions across multi-turn, cross-session interactions."

Core behaviors:
  1. On session start: recall relevant context from memory
  2. During conversation: store facts, decisions, preferences, lessons
  3. On session end: reflect on new knowledge, compound insights
  4. Confidence decay: old unverified facts lose confidence over time
  5. Cross-session learning: agent gets smarter about YOUR codebase

Usage:
  # With Engram-rs (self-hosted, MIT):
  MEMORY_BACKEND=engram python -m agent.main

  # With Elastic (cloud):
  MEMORY_BACKEND=elastic python -m agent.main
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.config import AgentConfig
from perseus_agent_core.memory import (
    ElasticMemoryBackend,
    EngramMemoryBackend,
    MemoryEntry,
    MemorySearchResult,
)
from perseus_agent_core.tools import DecisionLogTool, KnowledgeGraphTool, ProjectContextTool


class LLMError(Exception):
    """Raised when LLM API call fails after retries."""

    def __init__(self, status_code: int, message: str, retryable: bool = False):
        self.status_code = status_code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


# ── LLM Client (OpenAI-compatible) ──────────────────────────────────────

class QwenClient:
    """Thin wrapper around OpenAI-compatible API for Qwen Cloud.

    Uses the DashScope international endpoint which supports the standard
    /v1/chat/completions OpenAI-compatible interface.
    """

    def __init__(self, config: AgentConfig):
        self.api_key = config.llm_api_key
        self.base_url = config.llm_base_url.rstrip("/")
        self.model = config.llm_model
        self.max_retries = 3

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """Send a chat completion request and return the response text.

        Retries on transient errors (429, 5xx) with exponential backoff.
        Raises LLMError on non-retryable failures or exhaustion.
        """
        import urllib.request
        import urllib.error

        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        data = json.dumps(body).encode()
        last_error = None

        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Authorization", f"Bearer {self.api_key}")
            req.add_header("Content-Type", "application/json")

            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    result = json.loads(r.read())
                    return result["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                status = e.code
                error_body = e.read().decode()[:500]
                # Retry on rate limits and server errors
                if status in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    delay = 2 ** attempt
                    await asyncio.sleep(delay)
                    last_error = f"[LLM Error {status}]: {error_body}"
                    continue
                raise LLMError(
                    status, error_body,
                    retryable=status in (429, 500, 502, 503, 504)
                )
            except Exception as e:
                if attempt < self.max_retries:
                    delay = 2 ** attempt
                    await asyncio.sleep(delay)
                    last_error = str(e)
                    continue
                raise LLMError(0, str(e), retryable=True)

        raise LLMError(0, last_error or "max retries exhausted", retryable=True)


# ── Memory Manager ─────────────────────────────────────────────────────

class MemoryManager:
    """Coordinates memory operations: store, recall, decay, reflect.

    Adds confidence decay — facts that aren't reinforced over time
    lose confidence, simulating "forgetting" of outdated information.
    This addresses a key MemoryAgent Track requirement: "timely forgetting
    of outdated information."
    """

    def __init__(self, memory_backend, config: AgentConfig):
        self.memory = memory_backend
        self.config = config
        self.session_memories: list[str] = []  # IDs stored this session

    async def recall_context(self, project: str, query: str = "",
                             max_tokens: int = 2000) -> str:
        """Recall relevant memories for the current conversation turn.

        Args:
            project: Project namespace to recall from.
            query: Search query (defaults to project name).
            max_tokens: Approximate token budget for recalled context.
        """
        results = await self.memory.recall(
            query=query or project,
            project=project,
            limit=self.config.recall_count,
            min_confidence=0.3,
        )

        if not results:
            return ""

        lines = ["[Recalled from memory:]"]
        estimated_tokens = 0
        for r in results:
            age = ""
            if r.entry.created_at:
                days = (datetime.now(timezone.utc) - r.entry.created_at).days
                age = f" ({days}d ago)" if days > 0 else " (today)"
            line = (
                f"  [{r.entry.category}] {r.entry.content}"
                f"{age} (confidence: {r.entry.confidence:.0%})"
            )
            # Budget: ~4 chars per token is a safe over-estimate for English
            estimated_tokens += len(line) // 4
            if estimated_tokens > max_tokens:
                break
            lines.append(line)
        return "\n".join(lines)

    async def store(self, content: str, category: str, project: str,
                    tags: list[str] = None, confidence: float = 0.8) -> str:
        """Store a new memory and track it for this session.

        Default confidence is 0.8 so facts can decay over time.
        Fully verified facts should be stored with confidence=1.0.
        """
        entry = MemoryEntry(
            id=f"mem-{int(time.time() * 1000)}",
            content=content,
            category=category,
            project=project,
            tags=tags or [],
            confidence=confidence,
            source_session=os.getenv("SESSION_ID", "demo"),
        )
        eid = await self.memory.remember(entry)
        self.session_memories.append(eid)
        return eid

    async def reflect_and_compound(self, project: str) -> list[str]:
        """Reflect on session memories, compound insights.

        After each session, the agent reviews what it learned and generates
        higher-level insights. This is the "institutional knowledge" step.
        """
        insights = await self.memory.reflect(project=project)
        compounds = []

        for insight in insights:
            if isinstance(insight, dict):
                summary = insight.get("summary", str(insight))
                compounds.append(summary)
                await self.store(
                    content=f"Insight: {summary}",
                    category="insight",
                    project=project,
                    tags=["compounded", "auto"],
                )

        return compounds


# ── The Agent ──────────────────────────────────────────────────────────

class PerseusQwenAgent:
    """A Qwen-powered agent that never forgets.

    Remembers project context, user preferences, architectural decisions,
    and lessons learned — compounding knowledge across every session.

    Designed for the Qwen Cloud Hackathon MemoryAgent Track.
    """

    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig()

        # Validate config
        issues = self.config.validate()
        if issues:
            for issue in issues:
                print(f"  ⚠ {issue}", file=sys.stderr)
            critical = [i for i in issues if "required" in i.lower()]
            if critical:
                raise ValueError(
                    "Missing required configuration. "
                    "Set DASHSCOPE_API_KEY in .env"
                )

        # Initialize LLM
        self.llm = QwenClient(self.config)

        # Select memory backend
        if self.config.memory_backend == "engram":
            self.memory_backend = EngramMemoryBackend()
        else:
            self.memory_backend = ElasticMemoryBackend()

        # Memory manager
        self.memory_mgr = MemoryManager(self.memory_backend, self.config)

        # Tools
        self.project_ctx = ProjectContextTool(self.memory_backend)
        self.decision_log = DecisionLogTool(self.memory_backend)
        self.knowledge_graph = KnowledgeGraphTool(self.memory_backend)

        # Session state
        self.session_id = None
        self.current_project = None

    # ── Session Lifecycle ──────────────────────────────────────────

    async def start_session(self, project: str) -> dict:
        """Begin a new session. Load context from memory."""
        self.session_id = f"session-{int(time.time())}"
        os.environ["SESSION_ID"] = self.session_id
        self.current_project = project

        # Reset per-session counters (Q-5: was never reset, causing cumulative counts)
        self.memory_mgr.session_memories = []

        # Health check
        health = await self.memory_backend.health_check()

        # Recall existing context
        context = await self.memory_mgr.recall_context(project)
        project_ctx = await self.project_ctx.get_project_context(project)

        return {
            "session_id": self.session_id,
            "project": project,
            "memory_health": health,
            "existing_memories": len(
                await self.memory_backend.recall(query=project, limit=100)
            ),
            "project_context": project_ctx,
        }

    async def process_message(self, user_message: str) -> str:
        """Process a user message with memory-augmented reasoning."""
        # 1. Recall relevant context
        recalled = await self.memory_mgr.recall_context(
            self.current_project, user_message
        )

        # 2. Build system prompt with memory (token-budgeted)
        system_prompt = self._build_system_prompt(recalled)

        # 3. Get LLM response
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await self.llm.chat(
                messages,
                max_tokens=self.config.llm_max_tokens,
            )
        except LLMError:
            return "[Error: LLM request failed after retries. Check your DASHSCOPE_API_KEY and network.]"

        # 4. Extract and store key facts (skip on LLM error)
        await self._auto_store(user_message, response)

        return response

    async def end_session(self) -> dict:
        """End the session — reflect, compound, and prepare for next time."""
        if not self.current_project:
            return {"status": "no active session"}

        # Reflect and compound insights
        compounds = []
        if self.config.auto_reflect:
            compounds = await self.memory_mgr.reflect_and_compound(
                self.current_project
            )

        # Apply confidence decay to old unverified facts
        await self._decay_confidence()

        return {
            "session_id": self.session_id,
            "memories_stored": len(self.memory_mgr.session_memories),
            "insights_compounded": len(compounds),
            "compounds": compounds,
        }

    # ── Helpers ────────────────────────────────────────────────────

    def _build_system_prompt(self, recalled_context: str = "") -> str:
        """Build the system prompt with persistent memory context.

        Token-budgeted: recalled context is limited to ~2000 chars of
        memory content, keeping total prompt well within Qwen's context window.
        """
        base = (
            "You are Perseus, a persistent memory agent powered by Qwen Cloud. "
            "You remember everything about the user's projects — their tech stack, "
            "conventions, decisions, preferences, and lessons learned. "
            "You get smarter every session because you never forget.\n\n"
            "Current project: {project}\n"
        ).format(project=self.current_project)

        if recalled_context:
            # Token budget: cap recalled context to ~2000 estimated tokens
            # (~4 chars per token for English text)
            max_context_chars = 8000
            if len(recalled_context) > max_context_chars:
                recalled_context = recalled_context[:max_context_chars] + "\n[... older memories truncated ...]"
            base += f"\n{recalled_context}\n\n"
            base += (
                "Use the recalled context above to give informed, "
                "context-aware responses. If the user mentions something "
                "you already know about, acknowledge it."
            )

        return base

    async def _auto_store(self, user_msg: str, response: str):
        """Automatically extract and store key facts from conversation.

        Skips extraction if the response is an error message.
        """
        # Skip if response is an error
        if response.startswith("[Error:") or response.startswith("[LLM Error"):
            return

        # Store the interaction itself as context
        await self.memory_mgr.store(
            content=f"User asked: {user_msg[:200]}",
            category="context",
            project=self.current_project,
            tags=["interaction"],
        )

        # Ask the LLM to extract key facts
        extract_prompt = (
            "Extract 1-3 key facts, decisions, or preferences from this "
            "conversation. Return as JSON array of objects with fields: "
            "content (the fact), category (fact/decision/preference/lesson), "
            "and tags (array of keywords). Only include genuinely new information "
            "that the agent didn't already know.\n\n"
            f"User: {user_msg}\n\nAssistant: {response[:500]}\n\n"
            "JSON:"
        )

        messages = [
            {"role": "system", "content": "You extract structured facts from conversations. Respond ONLY with a JSON array."},
            {"role": "user", "content": extract_prompt},
        ]

        try:
            result = await self.llm.chat(messages, temperature=0.3, max_tokens=500)
            if result.startswith("[Error:") or result.startswith("[LLM Error"):
                return
            result = result.strip()
            if result.startswith("```"):
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[4:]
            facts = json.loads(result)
            if isinstance(facts, list):
                for fact in facts:
                    await self.memory_mgr.store(
                        content=fact["content"],
                        category=fact.get("category", "fact"),
                        project=self.current_project,
                        tags=fact.get("tags", []),
                    )
        except Exception:
            pass  # Best-effort extraction

    async def _decay_confidence(self):
        """Reduce confidence of old, unverified memories.

        Memories that haven't been accessed or reinforced in a while
        slowly lose confidence. If confidence drops below 0.3, they're
        effectively "forgotten" (excluded from recall).

        Q-2 fix: Now actually writes back decayed confidence values
        instead of computing them and hitting `pass`.
        """
        all_memories = await self.memory_backend.recall(
            query=self.current_project, limit=1000
        )

        now = datetime.now(timezone.utc)
        decay_rate = self.config.confidence_decay_rate
        decayed_count = 0

        for result in all_memories:
            entry = result.entry

            # Fully confident facts don't decay — they're verified
            if entry.confidence >= 1.0:
                continue

            age_days = 0
            if entry.updated_at:
                age_days = (now - entry.updated_at).days

            if age_days > 1:
                new_confidence = max(0.0, entry.confidence - decay_rate * age_days)
                if new_confidence < entry.confidence:
                    # Re-store the memory with reduced confidence
                    entry.confidence = new_confidence
                    entry.updated_at = now
                    try:
                        await self.memory_backend.remember(entry)
                        decayed_count += 1
                    except Exception:
                        pass  # Best-effort decay; don't fail session end

        if decayed_count:
            print(f"  [decay] Reduced confidence on {decayed_count} memories",
                  file=sys.stderr)


# ── Demo Runner ─────────────────────────────────────────────────────────

async def run_demo():
    """Run a 3-session demo showing memory compounding across sessions.

    Session 1: User introduces their project — agent learns the basics
    Session 2: User asks a follow-up — agent recalls and builds on prior knowledge
    Session 3: User asks a complex question — agent compounds knowledge from sessions 1+2
    """
    config = AgentConfig()
    agent = PerseusQwenAgent(config)

    project = "demo-project"

    print("=" * 60)
    print("  PERSEUS QWEN MEMORY AGENT — 3-Session Demo")
    print("  Qwen Cloud Hackathon 2026 — MemoryAgent Track")
    print("=" * 60)

    # ── Session 1: Introduce the project ──────────────────────────
    print("\n── Session 1: Project Introduction ──")
    s1 = await agent.start_session(project)
    print(f"  Session: {s1['session_id']}")
    print(f"  Existing memories: {s1['existing_memories']}")
    print(f"  Memory health: {s1['memory_health']['status']}")

    await agent.project_ctx.set_project_context(
        project=project,
        stack={"language": "Python 3.12", "framework": "FastAPI",
               "database": "PostgreSQL", "cache": "Redis",
               "deploy": "Docker + Kubernetes"},
        conventions=[
            "Use async/await for all I/O",
            "Type hints on all public functions",
            "Pytest for testing, pytest-cov for coverage",
            "Black for formatting, 100 char line length",
        ],
        architecture="Microservices with API gateway. Separate services for auth, "
                     "billing, and core API. Event-driven with RabbitMQ.",
    )
    print("  → Stored project context (stack, conventions, architecture)")

    response1 = await agent.process_message(
        "What should I know about my project before I start coding today?"
    )
    print(f"  Qwen: {response1[:300]}...")

    e1 = await agent.end_session()
    print(f"  End session 1 — stored {e1['memories_stored']} memories")

    # ── Session 2: Follow-up, agent should recall ──────────────────
    print("\n── Session 2: Follow-up (next day) ──")
    s2 = await agent.start_session(project)
    print(f"  Session: {s2['session_id']}")
    print(f"  Existing memories: {s2['existing_memories']}")
    print(f"  Project context recall: {len(s2['project_context'].get('conventions', []))} conventions found")

    await agent.decision_log.log_decision(
        project=project,
        decision="Use pgvector for vector search instead of Pinecone",
        rationale="PostgreSQL already in stack; pgvector avoids additional "
                  "operational complexity and vendor lock-in",
        alternatives=["Pinecone", "Weaviate", "pgvector"],
        context="Need semantic search for document retrieval",
    )
    print("  → Logged architectural decision (pgvector over Pinecone)")

    response2 = await agent.process_message(
        "Given that we decided on pgvector yesterday, how should I structure "
        "the search API endpoint?"
    )
    print(f"  Qwen: {response2[:300]}...")

    e2 = await agent.end_session()
    print(f"  End session 2 — stored {e2['memories_stored']} memories")

    # ── Session 3: Complex query, compound knowledge ───────────────
    print("\n── Session 3: Knowledge Compounding (one week later) ──")
    s3 = await agent.start_session(project)
    print(f"  Session: {s3['session_id']}")
    print(f"  Existing memories: {s3['existing_memories']}")

    response3 = await agent.process_message(
        "I need to onboard a new developer. Based on everything you know "
        "about this project, what should I tell them? Include stack, "
        "conventions, architecture, and key decisions."
    )
    print(f"  Qwen: {response3[:500]}...")

    e3 = await agent.end_session()
    print(f"  End session 3 — stored {e3['memories_stored']} memories")
    print(f"  Compounds: {e3['insights_compounded']}")

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  DEMO COMPLETE")
    print(f"  Total sessions: 3")
    print(f"  Total memories stored: "
          f"{e1['memories_stored'] + e2['memories_stored'] + e3['memories_stored']}")
    print(f"  Insights compounded: {e3['insights_compounded']}")
    print("=" * 60)
    print("\n  The agent REMEMBERS across sessions:")
    print("  • Project stack (Python, FastAPI, PostgreSQL, Redis, K8s)")
    print("  • Coding conventions (async/await, type hints, pytest, Black)")
    print("  • Architecture (microservices, API gateway, RabbitMQ)")
    print("  • Key decision (pgvector over Pinecone)")
    print("  • Cross-session compounding — agent gets smarter over time")
    print()
    print("  Backend: " + config.memory_backend)
    print("  LLM: Qwen Cloud (" + config.llm_model + ")")
    print()


if __name__ == "__main__":
    asyncio.run(run_demo())
