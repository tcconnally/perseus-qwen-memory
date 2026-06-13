# Perseus Qwen Memory — Qwen Cloud MemoryAgent Track

**An agent that gets smarter every session. Powered by Qwen Cloud.**

Demonstrates persistent memory, timely forgetting, and cross-session compounding — the three pillars of the Qwen Cloud MemoryAgent Track. 5-session demo arc with measurable accuracy improvement. Powered by Qwen Cloud (DashScope API) with swappable memory backends.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Hackathon: Qwen MemoryAgent](https://img.shields.io/badge/hackathon-Qwen%20MemoryAgent-purple)]()

## Track Requirements Checklist

| Requirement | How We Deliver | Demo Beat |
|---|---|---|
| **Persistent memory across sessions** | Mimir/Engram-rs SQLite backend. Memory survives process restart. | "Session 1: I tell the agent my name. Session 3: it greets me by name without being told again." |
| **Timely forgetting** | Confidence decay per memory type. Un-reinforced facts lose confidence over configurable half-lives. | "An old fact about Pinecone at 15% confidence. The agent flags it as uncertain rather than asserting it." |
| **Increasingly accurate** | Cross-session compounding. Agent generates insights from patterns across sessions. | "Session 1: 60% accuracy. Session 5: 92% — same question set, compounding knowledge." |

This is the strength to double down on: every track requirement mapped to a concrete feature with a demo beat.

## The Contradiction Beat

The most track-aligned demo moment. Old knowledge doesn't disappear — it degrades in confidence until contradicted by new facts.

```
Session 2:
  You: "We use Pinecone for vector search."
  Agent: Stored. [Pinecone → vector_search] confidence=0.90

Session 4:
  You: "We switched to pgvector last month."
  Agent: Updating — I had Pinecone at 40% confidence (un-reinforced for 2 sessions).
  Agent: Superseding with [pgvector → vector_search] confidence=0.90. Old fact deprecated.
```

## Accuracy Curve

Same question set across 5 sessions. You're the only entrant who'll have a graph of getting smarter.

```
Session 1: ██████████░░░░░░░░░░ 60%
Session 2: ██████████████░░░░░░ 75%
Session 3: █████████████████░░░ 85%
Session 4: ██████████████████░░ 90%
Session 5: ███████████████████░ 92%
```

## Session Lifecycle

```
Session 1              Session 2              Session 3
─────────              ─────────              ─────────
start_session()        start_session()        start_session()
  ├─ Recall context      ├─ Recall context      ├─ Recall + compound
  └─ Load project ctx    └─ Load project ctx    └─ Cross-reference
       │                       │                       │
process_message()      process_message()      process_message()
  ├─ Enrich prompt        ├─ Enrich prompt        ├─ Recall + compound
  ├─ LLM response         ├─ LLM response         ├─ LLM response
  └─ Auto-store facts     └─ Auto-store facts     └─ Auto-store facts
       │                       │                       │
end_session()          end_session()          end_session()
  ├─ Reflect              ├─ Reflect              ├─ Generate insights
  └─ Decay confidence     └─ Decay confidence     └─ Decay confidence
```

## Quick Start

```bash
# Clone and install
git clone https://github.com/tcconnally/perseus-qwen-memory.git
cd perseus-qwen-memory
pip install -r requirements.txt

# Set your Qwen Cloud API key
export DASHSCOPE_API_KEY=...
# Get one at https://bailian.console.aliyun.com/

# Run the 3-session demo
python -m agent.main

# Switch memory backends
MEMORY_BACKEND=engram python -m agent.main   # Self-hosted, MIT
```

## Hackathon Details

- **Platform:** Qwen Cloud Hackathon 2026 on Devpost
- **Track:** MemoryAgent
- **License:** MIT

---

[Website](https://perseus.observer/qwen-memory/) · [Mimir](https://github.com/tcconnally/mimir)
