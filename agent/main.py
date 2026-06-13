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


# ── LLM Client (OpenAI-compatible) ──────────────────────────────────────

class LLMError(RuntimeError):
    """A chat completion failed.

    Raised instead of returning error text as if it were model output —
    error strings must never flow into process_message responses or get
    persisted as "memories" by _auto_store.
    """

    def __init__(self, message: str, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class QwenClient:
    """Thin wrapper around OpenAI-compatible API for Qwen Cloud.

    Uses the DashScope international endpoint which supports the standard
    /v1/chat/completions OpenAI-compatible interface. Rate limits (429)
    and transient 5xx/network errors are retried with exponential
    backoff; everything else raises LLMError immediately.
    """

    MAX_RETRIES = 3  # 4 attempts total; backoff 1s, 2s, 4s between them

    def __init__(self, config: AgentConfig):
        self.api_key = config.llm_api_key
        self.base_url = config.llm_base_url.rstrip("/")
        self.model = config.llm_model

    def _request_sync(self, url: str, data: bytes) -> dict:
        """Perform a single synchronous HTTP request (blocking I/O).

        Extracted so chat() can wrap it in asyncio.to_thread() — keeps
        the event loop free for concurrent work while this blocks.
        """
        import urllib.error
        import urllib.request

        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:300]
            except Exception:
                pass
            raise LLMError(
                f"LLM request failed with HTTP {e.code}: {detail}",
                status=e.code,
                retryable=(e.code == 429 or e.code >= 500),
            ) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LLMError(f"LLM network error: {e}", retryable=True) from e

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """Send a chat completion request and return the response text.

        The blocking I/O (urllib) runs on a worker thread via
        asyncio.to_thread() so the event loop stays responsive even
        during the 60s timeout on the remote call.
        """
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        data = json.dumps(body).encode()

        last_error: LLMError | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            if attempt:
                await asyncio.sleep(2 ** (attempt - 1))  # 1s, 2s, 4s

            try:
                result = await asyncio.to_thread(self._request_sync, url, data)
                return result["choices"][0]["message"]["content"]
            except LLMError as e:
                if not e.retryable:
                    raise
                last_error = e
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                raise LLMError(f"LLM returned malformed response: {e}") from e

        raise last_error or LLMError("LLM request failed")


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

    async def recall_context(self, project: str, query: str = "") -> str:
        """Recall relevant memories for the current conversation turn.

        Output is budgeted to config.max_context_chars: as memories
        compound across sessions, an unbounded block would grow the
        system prompt until the model's context window 400s. The
        highest-confidence memories are kept; the rest are dropped with
        an explicit truncation note.
        """
        results = await self.memory.recall(
            query=query or project,
            project=project,
            limit=self.config.recall_count,
            min_confidence=0.3,  # Skip very low-confidence memories
        )

        if not results:
            return ""

        # Highest-confidence first, so the budget keeps the best facts.
        ordered = sorted(results, key=lambda r: r.entry.confidence, reverse=True)

        budget = self.config.max_context_chars
        header = "[Recalled from memory:]"
        lines = [header]
        used = len(header)
        shown = 0
        for r in ordered:
            age = ""
            if r.entry.created_at:
                days = (datetime.now(timezone.utc) - r.entry.created_at).days
                age = f" ({days}d ago)" if days > 0 else " (today)"
            line = (
                f"  [{r.entry.category}] {r.entry.content}"
                f"{age} (confidence: {r.entry.confidence:.0%})"
            )
            if used + len(line) + 1 > budget:
                break
            lines.append(line)
            used += len(line) + 1
            shown += 1

        if shown < len(ordered):
            lines.append(
                f"  (showing top {shown} of {len(ordered)} memories — "
                "lower-confidence entries omitted to fit the context budget)"
            )
        return "\n".join(lines)

    async def store(self, content: str, category: str, project: str,
                    tags: list[str] = None, confidence: float = 0.9) -> str:
        """Store a new memory and track it for this session.

        Default confidence is 0.9, not 1.0: decay skips fully-confident
        facts, so 1.0 is reserved for explicitly verified information —
        everything else must be able to age out.
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

    @staticmethod
    def _topic_tokens(text: str) -> set[str]:
        stop = {
            "a", "an", "and", "are", "for", "in", "is", "it", "of", "on",
            "or", "our", "the", "to", "we", "with",
        }
        return {
            t for t in "".join(
                c.lower() if c.isalnum() else " " for c in text
            ).split()
            if t not in stop
        }

    async def detect_contradictions(self, project: str, new_fact: str,
                                    category: str = "fact") -> list[dict]:
        """Find stored memories that the new fact contradicts.

        Same-topic detection is token overlap (Jaccard) within the same
        category: enough shared vocabulary to be about the same thing,
        but different content. Returns details for each hit so callers
        can announce what's being superseded.
        """
        results = await self.memory.recall(
            query=new_fact, project=project, category=category, limit=5,
        )
        new_tokens = self._topic_tokens(new_fact)
        if not new_tokens:
            return []

        contradictions = []
        for r in results:
            old = r.entry
            if old.content.strip() == new_fact.strip():
                continue  # identical restatement, not a contradiction
            old_tokens = self._topic_tokens(old.content)
            if not old_tokens:
                continue
            overlap = len(new_tokens & old_tokens) / len(new_tokens | old_tokens)
            if overlap >= 0.3:
                age_days = 0
                if old.created_at:
                    age_days = (datetime.now(timezone.utc) - old.created_at).days
                contradictions.append({
                    "id": old.id,
                    "content": old.content,
                    "old_confidence": old.confidence,
                    "age_days": age_days,
                    "overlap": round(overlap, 2),
                    "entry": old,
                })
        return contradictions

    async def supersede(self, project: str, new_fact: str,
                        category: str = "fact",
                        tags: list[str] = None) -> dict:
        """Store a fact, demoting any same-topic memories it contradicts.

        The "timely forgetting" path: the old fact drops to 0.2
        confidence (below the 0.3 recall floor — effectively forgotten,
        but recoverable), and the new fact comes in at 0.9.
        """
        contradictions = await self.detect_contradictions(
            project, new_fact, category=category
        )
        for c in contradictions:
            old = c["entry"]
            old.confidence = 0.2
            await self.memory.remember(old)  # write-back via id upsert

        new_id = await self.store(
            new_fact, category, project, tags=tags, confidence=0.9
        )
        return {
            "id": new_id,
            "superseded": [
                {k: c[k] for k in ("id", "content", "old_confidence", "age_days")}
                for c in contradictions
            ],
        }

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
        # Per-session bookkeeping: without this reset, end_session's
        # memories_stored count accumulates across sessions.
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

        # 2. Build system prompt with memory
        system_prompt = self._build_system_prompt(recalled)

        # 3. Get LLM response
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await self.llm.chat(messages)
        except LLMError as e:
            # Clean failure: never present error text as the agent's
            # answer, and never let _auto_store persist it as a memory.
            print(f"  ⚠ LLM unavailable: {e}", file=sys.stderr)
            return (
                "I couldn't reach the language model just now "
                f"({e}). Your message was not lost — please retry."
            )

        # 4. Extract and store key facts from the conversation
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
        decayed = await self._decay_confidence()
        for d in decayed:
            marker = "forgotten" if d["forgotten"] else "decayed"
            print(
                f"  ~ {marker}: \"{d['content']}\" "
                f"{d['from']:.0%} → {d['to']:.0%} ({d['age_days']}d old)"
            )

        return {
            "session_id": self.session_id,
            "memories_stored": len(self.memory_mgr.session_memories),
            "insights_compounded": len(compounds),
            "compounds": compounds,
            "memories_decayed": len(decayed),
            "decayed": decayed,
        }

    # ── Helpers ────────────────────────────────────────────────────

    def _build_system_prompt(self, recalled_context: str = "") -> str:
        """Build the system prompt with persistent memory context."""
        base = (
            "You are Perseus, a persistent memory agent powered by Qwen Cloud. "
            "You remember everything about the user's projects — their tech stack, "
            "conventions, decisions, preferences, and lessons learned. "
            "You get smarter every session because you never forget.\n\n"
            "Current project: {project}\n"
        ).format(project=self.current_project)

        if recalled_context:
            base += f"\n{recalled_context}\n\n"
            base += (
                "Use the recalled context above to give informed, "
                "context-aware responses. If the user mentions something "
                "you already know about, acknowledge it."
            )

        return base

    async def _auto_store(self, user_msg: str, response: str):
        """Automatically extract and store key facts from conversation."""
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
            # Try to parse JSON from response
            result = result.strip()
        except LLMError as e:
            # Extraction is best-effort, but an LLM failure must never be
            # stored as a "memory" — skip extraction for this turn.
            print(f"  ⚠ fact extraction skipped (LLM error): {e}", file=sys.stderr)
            return
        try:
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

    async def _decay_confidence(self) -> list[dict]:
        """Reduce confidence of old, unverified memories and write it back.

        Memories that haven't been reinforced lose confidence with age
        (config.confidence_decay_rate per day, starting after 1 day).
        Below 0.3 they're effectively "forgotten" — excluded from recall
        by the min_confidence floor. Facts at exactly 1.0 are pinned:
        that value is reserved for explicitly verified information
        (everything else is stored at 0.9 so it CAN age out).

        Age is measured from created_at, not updated_at — the write-back
        itself touches updated_at, which would otherwise reset the clock
        on every decay pass.

        Returns details of each decayed memory for session reporting.
        """
        all_memories = await self.memory_backend.recall(
            query=self.current_project, limit=1000
        )

        now = datetime.now(timezone.utc)
        decay_rate = self.config.confidence_decay_rate

        decayed = []
        for result in all_memories:
            entry = result.entry
            if entry.confidence >= 1.0:
                continue  # pinned: explicitly verified facts don't decay

            age_days = 0
            if entry.created_at:
                age_days = (now - entry.created_at).days
            elif entry.updated_at:
                age_days = (now - entry.updated_at).days

            if age_days > 1:  # Decay starts after 1 day
                new_confidence = max(0.0, entry.confidence - decay_rate * age_days)
                if new_confidence < entry.confidence:
                    old_confidence = entry.confidence
                    entry.confidence = new_confidence
                    # Write-back: remember() upserts by id on both backends.
                    await self.memory_backend.remember(entry)
                    decayed.append({
                        "id": entry.id,
                        "content": entry.content[:80],
                        "from": round(old_confidence, 2),
                        "to": round(new_confidence, 2),
                        "age_days": age_days,
                        "forgotten": new_confidence < 0.3,
                    })
        return decayed


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

    # Seed a fact that will be contradicted in Session 3 — the
    # "timely forgetting" beat.
    await agent.memory_mgr.store(
        content="We use Pinecone for vector search",
        category="fact",
        project=project,
        tags=["vector-db"],
    )
    print("  → Stored fact: \"We use Pinecone for vector search\" (90% confidence)")

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

    # ── Contradiction beat: the agent updates its own beliefs ──────
    update = await agent.memory_mgr.supersede(
        project=project,
        new_fact="We switched to pgvector for vector search",
        tags=["vector-db"],
    )
    for old in update["superseded"]:
        age = f"{old['age_days']}d ago" if old["age_days"] else "earlier"
        print(
            f"  🔄 Updating — I had \"{old['content']}\" at "
            f"{old['old_confidence']:.0%} confidence from {age}; "
            f"superseding it (now 20% — effectively forgotten)."
        )
    if not update["superseded"]:
        print("  → Stored: \"We switched to pgvector for vector search\"")

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
