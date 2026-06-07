# Perseus Qwen Memory Agent

> **Qwen Cloud Hackathon 2026 — MemoryAgent Track**
>
> *"Your AI agent shouldn't have amnesia."*

A Qwen Cloud-powered agent that builds **persistent, evolving memory** across sessions — remembering project context, user preferences, architectural decisions, and lessons learned so the agent gets smarter every time you talk to it.

Built with **Qwen Cloud** (via DashScope OpenAI-compatible API) for the memory track, with swappable memory backends: **Elastic Cloud** (managed) or **Engram-rs** (self-hosted, MIT).

---

## The Problem

Every time you start a new session with an AI agent, you spend the first 10 minutes re-explaining your project. Your stack. Your conventions. Your decisions. The agent has amnesia.

## The Solution

**Perseus Qwen Memory Agent** gives agents persistent, compounding memory:

- **Remembers** your project stack, conventions, and architectural decisions
- **Recalls** past debugging sessions, decisions, and their rationale
- **Compounds** knowledge — the agent spots patterns across sessions
- **Forgets wisely** — old unverified facts lose confidence ("timely forgetting")
- **Switches backends** — Elastic (managed) or Engram-rs (self-hosted, MIT)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Qwen Cloud                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Perseus Memory Agent                  │  │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────────────┐  │  │
│  │  │  Qwen   │  │  Memory  │  │  Memory Backend   │  │  │
│  │  │  Max    │◄─┤  Manager ├──┤  ┌────────────┐  │  │  │
│  │  │         │  │          │  │  │ Elastic    │  │  │  │
│  │  └─────────┘  └──────────┘  │  │ (MCP)      │  │  │  │
│  │       │                     │  ├────────────┤  │  │  │
│  │       ▼                     │  │ Engram-rs  │  │  │  │
│  │  ┌──────────┐               │  │ (OSS, MIT) │  │  │  │
│  │  │  Tools   │               │  └────────────┘  │  │  │
│  │  └──────────┘               └──────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Memory Operations

| Operation | Description | Elastic Backend | Engram-rs Backend |
|---|---|---|---|
| `remember` | Store facts, decisions, context | Elasticsearch index | SQLite via engram CLI |
| `recall` | Search memory with filters | Elastic hybrid search | FTS5 text search |
| `forget` | Remove outdated/incorrect facts | Delete by ID | Remove entry |
| `reflect` | Cross-reference, find patterns | ES|QL aggregations | SQL queries |
| `decay` | Confidence decay over time | Update metadata | Update metadata |

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/tcconnally/perseus-qwen-memory.git
cd perseus-qwen-memory
pip install -r requirements.txt

# 2. Set your Qwen Cloud API key
export DASHSCOPE_API_KEY=***# Get one at https://bailian.console.aliyun.com/

# 3. Run the demo (3-session memory compounding)
python -m agent.main

# 4. Switch memory backends
MEMORY_BACKEND=engram python -m agent.main   # Self-hosted, MIT
MEMORY_BACKEND=elastic python -m agent.main  # Managed cloud
```

---

## Session Lifecycle

```
Session 1                  Session 2                  Session 3
─────────                  ─────────                  ─────────
start_session()            start_session()            start_session()
  ├─ Health check            ├─ Health check            ├─ Health check
  ├─ Recall context          ├─ Recall context          ├─ Recall context
  └─ Load project ctx        └─ Load project ctx        └─ Load + compound
       │                           │                           │
process_message()          process_message()          process_message()
  ├─ Recall relevant          ├─ Recall relevant          ├─ Recall + compound
  ├─ Enrich prompt            ├─ Enrich prompt            ├─ Cross-reference
  ├─ LLM response             ├─ LLM response             ├─ LLM response
  └─ Auto-store facts         └─ Auto-store facts         └─ Auto-store facts
       │                           │                           │
end_session()              end_session()              end_session()
  ├─ Reflect                  ├─ Reflect                  ├─ Reflect
  ├─ Compound insights        ├─ Compound insights        ├─ Generate insights
  └─ Decay confidence         └─ Decay confidence         └─ Decay confidence
```

---

## Why Qwen Cloud + MemoryAgent Track

The Qwen Cloud Hackathon MemoryAgent Track calls for an agent that:

1. **Accumulates experience across sessions** — Perseus stores every interaction
2. **Remembers user preferences** — Auto-extracts and stores preferences
3. **Makes increasingly accurate decisions** — Compounds knowledge over time
4. **Efficient memory storage/retrieval** — FTS5 + abstract backend
5. **Timely forgetting of outdated info** — Confidence decay system
6. **Recalls critical memories in limited context windows** — Relevance-scored recall with configurable limits

---

## What's Next

- **Multi-project awareness** — Cross-project pattern recognition
- **Memory compression** — Summarize old memories for efficient storage
- **MCP-native Engram-rs** — Direct MCP server for plug-and-play integration
- **Hierarchical memory** — Working → Short-term → Long-term memory tiers

---

## License

MIT — see [LICENSE](LICENSE)

---

Built for the [Qwen Cloud Hackathon 2026](https://qwencloud-hackathon.devpost.com/) — MemoryAgent Track.
