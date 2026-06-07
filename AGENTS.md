# AGENTS.md — Project Context for AI Agents

## Project Identity
- **Name:** Perseus Qwen Memory Agent
- **Purpose:** Qwen Cloud Hackathon 2026 — MemoryAgent Track submission
- **Stack:** Python 3.12, Qwen Cloud (OpenAI-compatible API), Engram-rs or Elastic
- **License:** MIT

## Architecture
- `agent/main.py` — Core agent loop (PerseusQwenAgent class) with 3-session demo
- `agent/memory/` — Abstract MemoryBackend + Elastic + Engram-rs implementations
- `agent/tools/` — Tools: project_context, decision_log, knowledge_graph
- `agent/config.py` — Single source of truth; switch backends by changing MEMORY_BACKEND

## Key Design Decisions
1. **Abstract MemoryBackend** — Both Elastic and Engram-rs implement the same interface. Backend swap = one env var.
2. **Confidence decay** — Old unverified facts lose confidence over time, implementing "timely forgetting"
3. **Session lifecycle** — start_session() loads context → process_message() with recall → end_session() with reflect
4. **Cross-session compounding** — Agent generates insights from patterns across sessions
5. **Memory categories** — fact, decision, preference, lesson, insight, context

## Conventions
- async/await for all I/O operations
- Type hints on all public methods
- MemoryEntry dataclass for all memory operations
- Tools are stateless; memory backend is the single state holder

## Quick Start
```bash
# 1. Set API key
export DASHSCOPE_API_KEY="your-key"

# 2. Run the demo
python -m agent.main

# 3. Switch to Engram-rs (self-hosted)
MEMORY_BACKEND=engram python -m agent.main
```
