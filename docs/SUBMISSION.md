# Devpost Submission — Perseus Qwen Memory Agent

**Hackathon:** Qwen Cloud Hackathon 2026 — MemoryAgent Track
**Deadline:** July 9, 2026
**Prize:** $70,000+ (cash + cloud credits)

---

## Step 1: Manage Team

- **Team:** tcconnally (solo)
- **Email:** (your email)

---

## Step 2: Project Overview

### Project Name

```
Perseus Qwen Memory Agent
```

### Elevator Pitch (max 200 chars)

```
Your AI agent shouldn't have amnesia. Perseus gives Qwen agents persistent, compounding memory across sessions — remembering your stack, decisions, and preferences. Elastic (cloud) or Engram-rs (self-hosted, MIT), one config line.
```

### Tagline

```
The agent that never forgets. Powered by Qwen Cloud.
```

---

## Step 3: Project Details

### What It Does

Perseus Qwen Memory Agent gives AI agents persistent, evolving memory so they remember project context across sessions. Instead of re-explaining your tech stack, conventions, and architectural decisions every time you start a new session, the agent recalls everything it learned about your project — even from weeks ago.

Key capabilities:
- **Remembers project context** — stack, conventions, architecture, preferences
- **Logs decisions with rationale** — why pgvector over Pinecone? The agent remembers
- **Compounds knowledge** — spots patterns across sessions, surfaces insights
- **Forgets wisely** — old unverified facts lose confidence over time
- **Swappable backends** — Elastic (managed cloud) or Engram-rs (self-hosted MIT), one config line

### How I Built It

Built with Qwen Cloud (via DashScope OpenAI-compatible API) for the LLM layer:

1. **Qwen Cloud integration** — Uses the standard `/v1/chat/completions` endpoint on Qwen Cloud international (dashscope-intl.aliyuncs.com). Model: qwen-max for optimal reasoning + memory synthesis.

2. **Memory abstraction layer** — Abstract `MemoryBackend` interface in Python. Two implementations: `ElasticMemoryBackend` (uses Elasticsearch) and `EngramMemoryBackend` (uses Engram-rs CLI / SQLite). Same API surface, swap backend by changing one environment variable.

3. **Session lifecycle** — `start_session()` loads all relevant context from memory. `process_message()` enriches every prompt with recalled memories. `end_session()` reflects on new knowledge, compounds insights, and applies confidence decay.

4. **Agent tools** — Three tools: `ProjectContextTool` (manage project stack/conventions), `DecisionLogTool` (log and recall architectural decisions with rationale), `KnowledgeGraphTool` (cross-reference memories, find patterns).

5. **Confidence decay** — Memories that aren't reinforced lose confidence over time. Below 0.3 confidence, memories are excluded from recall — implementing "timely forgetting."

6. **Cross-session compounding** — After each session, the agent reflects on what it learned and generates higher-level insights. These compounds make the agent smarter over time.

### Why Qwen Cloud

Qwen Cloud was the natural choice for the MemoryAgent Track because:

1. **MemoryAgent Track alignment** — The track specifically calls for "persistent memory that accumulates experience across multi-turn, cross-session interactions." Perseus was built for exactly this use case.

2. **Qwen Max's reasoning capabilities** — The memory extraction and compounding pipeline relies on strong reasoning. Qwen Max excels at structured extraction from conversations and cross-referencing stored knowledge.

3. **OpenAI-compatible API** — Standard `/v1/chat/completions` means zero vendor lock-in. The agent can swap to any OpenAI-compatible provider by changing `LLM_BASE_URL`.

4. **DashScope ecosystem** — Free credits for hackathon participants, global endpoint availability, and growing model family.

### What's Next

- **Multi-project awareness** — Agent recognizes cross-project patterns (e.g., "you use this same auth pattern in 3 repos")
- **Memory compression** — Summarize old memories into compact embeddings for efficient long-term storage
- **Hierarchical memory** — Working memory → Short-term → Long-term tiers with automatic promotion/eviction
- **MCP-native Engram-rs** — Direct MCP server in Engram-rs for zero-config integration with any MCP-compatible platform

---

## Step 4: Additional Info

### GitHub Repository

```
https://github.com/tcconnally/perseus-qwen-memory
```

### Demo Video

_(YouTube link — 3-minute demo showing 3-session memory compounding)_

### Track

**MemoryAgent Track** — Build an Agent with persistent memory that autonomously accumulates experience, remembers user preferences, and makes increasingly accurate decisions across multi-turn, cross-session interactions.

### Open Source License

MIT — visible in repo root and About section

### Built With

- Qwen Cloud (qwen-max via DashScope OpenAI-compatible API)
- Python 3.12
- Engram-rs (self-hosted memory, MIT)
- Elastic Cloud (managed memory)
- Pydantic (configuration)

---

## Step 5: Submit

### Checklist

- [ ] Public GitHub repo with MIT license at top
- [ ] Working demo (3-session memory compounding)
- [ ] ~3 minute demo video showing cross-session recall
- [ ] MemoryAgent Track requirements demonstrated:
  - [ ] Persistent memory across sessions
  - [ ] Accumulating experience (more accurate in session 3 than session 1)
  - [ ] Remembering user preferences
  - [ ] Timely forgetting (confidence decay)
  - [ ] Recall within limited context windows
- [ ] All Devpost form fields completed
- [ ] Hosted demo or runnable instructions
