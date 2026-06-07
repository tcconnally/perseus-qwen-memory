# Devpost Description Rewrite — perseus-lroea6 (Qwen Cloud Hackathon)

Copy these sections into the Devpost form. The demo video is now correct (Perseus Qwen Memory Agent, 2:50).

---

## Project Name
```
Perseus Qwen Memory Agent
```

## Elevator Pitch (max 200 chars)

```
AI agents shouldn't have amnesia. Perseus gives Qwen agents persistent, compounding memory across sessions — remembering your stack, decisions, and preferences. Elastic (cloud) or Engram-rs (self-hosted, MIT), one config line.
```

---

## What It Does

**Perseus Qwen Memory Agent gives AI agents persistent, evolving memory that compounds across sessions.** Instead of re-explaining your tech stack, conventions, and architectural decisions every time you start a new session, the agent recalls everything it learned about your project — even from weeks ago.

Key capabilities for the **MemoryAgent Track:**

- **Persistent project memory** — remembers stack, conventions, architecture, preferences across sessions
- **Cross-session compounding** — the agent gets smarter over time, synthesizing higher-level insights from patterns it spots
- **Confidence decay** — old unverified facts lose confidence over time, implementing "timely forgetting" so the agent's memory stays relevant
- **Swappable backends** — Elastic Cloud (managed) or Engram-rs (self-hosted, MIT), one environment variable to switch. Same API, same results.
- **Session lifecycle** — start_session() recalls context, process_message() enriches every prompt, end_session() reflects and compounds

The agent demonstrated a 3-session progression:
1. **Session 1** — learns project context from scratch (8 facts stored)
2. **Session 2** — recalls prior knowledge, logs decisions with rationale
3. **Session 3** — compounds everything into a comprehensive project summary, generates cross-session insights

---

## How I Built It

Built with **Qwen Max** via the **Alibaba Cloud DashScope** API, deployed on an Alibaba Cloud ECS instance:

1. **Qwen Cloud LLM** — Uses the DashScope international endpoint (`dashscope-intl.aliyuncs.com/compatible-mode/v1`). Standard OpenAI-compatible `/v1/chat/completions` interface means zero vendor lock-in.

2. **Perseus Context Engine** — Implements the "Resolve-Before-Context" protocol: pre-computes workspace state, resolves file dependencies, and enforces security gating *before* the agent sees its prompt. 22+ auto-discovered MCP tools with zero manual wiring.

3. **Memory Backend Abstraction** — An abstract `MemoryBackend` interface (`remember`, `recall`, `forget`, `reflect`) with two implementations:
   - `ElasticMemoryBackend` — managed cloud, hybrid search (semantic + BM25)
   - `EngramMemoryBackend` — self-hosted, MIT-licensed, SQLite + FTS5

4. **Dual-Factor Security** — Dangerous shell commands are gated by both a config flag (`allow_query_shell`) AND an environment variable (`PERSEUS_ALLOW_DANGEROUS`). Prompt injection cannot trigger shell access.

5. **Agent Tools** — Three MCP-callable tools: `ProjectContextTool` (stack/conventions), `DecisionLogTool` (architectural decisions with rationale), `KnowledgeGraphTool` (cross-reference memories, compound knowledge).

---

## Why Qwen Cloud

Qwen Cloud was chosen for the MemoryAgent Track because:

- **MemoryAgent alignment** — The track specifically calls for "persistent memory that accumulates experience across multi-turn, cross-session interactions." Perseus was architected for exactly this use case.

- **Qwen Max's reasoning** — The memory extraction and compounding pipeline requires strong structured reasoning. Qwen Max excels at extracting facts from conversations and cross-referencing stored knowledge.

- **OpenAI-compatible API** — Standard `/v1/chat/completions` means the agent can swap to any compatible provider by changing `LLM_BASE_URL` — no code changes.

- **Alibaba Cloud deployment** — Deployed on Alibaba Cloud ECS, using DashScope international endpoint for global availability.

---

## What's Next

- **Distributed Memory** — Multi-agent societies exchanging "experience shards" via a shared persistent store
- **Memory Compression** — Summarize old memories into compact embeddings for efficient long-term storage
- **EdgeAgent Integration** — Port the core resolution engine to low-power hardware (Track 5 alignment)
- **Governance Dashboard** — Real-time observability for agent context resolution paths

---

## Built With

- **Qwen Cloud** (qwen-max via DashScope API)
- **Python 3.12** (Modular registry-driven architecture)
- **MCP** (Model Context Protocol — 22+ auto-discovered tools)
- **Engram-rs** (Self-hosted memory, MIT, Rust + SQLite + FTS5)
- **Elastic Cloud** (Managed memory, hybrid search)
- **Alibaba Cloud ECS** (Deployment)
- **Pydantic** (Configuration management)
