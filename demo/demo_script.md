# Demo Script — Perseus Qwen Memory Agent

**Duration:** ~2:50 | **Format:** Terminal simulation, recorded 1280×720 MP4

---

## Scene 1: Session 1 — Project Onboarding (0:00–0:40)

**Visual:** Dark terminal. Green "●" agent and blue "▸" user prompts.

**Narration:**
> "Every AI agent has amnesia. Every new session, you re-explain your project from scratch. Perseus fixes this. Watch."

1. Agent starts session — 0 existing memories.
2. User introduces project: "Python, FastAPI, PostgreSQL, Redis, Docker + K8s."
3. Agent stores 8 facts: stack, conventions, architecture — badges appear in yellow.
4. User asks about conventions. Agent responds using just-stored knowledge.
5. Session 1 ends: 8 memories stored.

**Key visual:** `[store]` badges appearing as each fact is persisted.

---

## Scene 2: Session 2 — Cross-Session Recall (0:40–1:20)

**Visual:** Same terminal, but now memories are recalled from prior session.

**Narration:**
> "Next day. New session. But the agent remembers."

1. Agent starts — loads 8 existing memories. Purple `[recall]` badges show retrieved context.
2. User asks: "Pinecone or pgvector?"
3. Agent answers using project context: "PostgreSQL is already in your stack — use pgvector."
4. Agent logs the decision with rationale.
5. User asks about endpoint structure. Agent combines stack knowledge + new decision.
6. Session 2 ends: 3 new memories, earlier memories reinforced.

**Key visual:** `[recall]` badges showing memories from "1d ago" — the agent isn't starting from zero.

---

## Scene 3: Session 3 — Knowledge Compounds (1:20–1:55)

**Visual:** Even more context retrieved. Purple `[insight]` badge appears.

**Narration:**
> "One week later. The agent compounds everything it's learned."

1. Agent starts — 11 memories across 3 categories.
2. User: "Onboard a new developer."
3. Agent delivers comprehensive summary: stack, architecture, conventions, key decisions — all from memory.
4. `[insight]` badges appear: "Python+PostgreSQL stack is consistent across 3 sessions" — the agent found a pattern on its own.
5. Session 3 ends: 2 insights compounded.

**Key visual:** The agent's response getting longer and more informed with each session. Badges showing `[store]` → `[recall]` → `[insight]` — the progression from learning to knowing.

---

## Scene 4: Backend Swap (1:55–2:15)

**Visual:** Blue `[swap]` badge. Same terminal, different backend.

**Narration:**
> "Same agent. Same code. Swap the backend in one config line."

1. `MEMORY_BACKEND=elastic` → `MEMORY_BACKEND=engram`
2. Engram-rs initializes: FTS5 search, SQLite-backed, MIT licensed.
3. Agent recalls same 13 memories — identical quality, zero cloud dependency.
4. "MIT licensed, no API keys, no cloud."

**Key visual:** The `[swap]` badge showing the backend transition. No code changes, just one env var.

---

## Scene 5: Closing (2:15–2:50)

**Visual:** Summary list, GitHub URL, hackathon name.

**Narration:**
> "Perseus Qwen Memory Agent: Persistent memory that compounds across sessions. Powered by Qwen Cloud. Backend-agnostic. MIT licensed. For the Qwen Cloud Hackathon 2026 — MemoryAgent Track."

1. Five checkmarks: persistent memory, compounding, confidence decay, swappable backends, Qwen Cloud.
2. GitHub URL: `github.com/tcconnally/perseus-qwen-memory`
3. MIT License badge.
4. Hackathon track name.

**Closing frame:** GitHub URL + Qwen Cloud + MIT license + MemoryAgent Track.
