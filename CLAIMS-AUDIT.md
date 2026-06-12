# Claims Audit — perseus-qwen-memory

**Date:** 2026-06-12 · **Audited:** README.md, AGENTS.md vs code on `main`

## Findings (ranked by judge visibility)

### CRITICAL (FIXED TODAY) — main crashed on import

The PR #7 merge reintroduced `id: str = ""` before required `MemoryEntry`
fields → `TypeError` on any `import agent.memory.backend`. Every demo path was
dead on `main`. Fixed and merged in
[PR #10](https://github.com/tcconnally/perseus-qwen-memory/pull/10); the new
smoke-test CI (`ci/smoke-tests` branch) catches this class of bug on every push.

### CRITICAL — Engram quickstart crashes against current engram-rs

- **Claim:** README quickstart: `MEMORY_BACKEND=engram python -m agent.main`.
- **Reality:** Same gap as perseus-rapid-agent — `EngramMemoryBackend` invokes CLI verbs removed in engram-rs v0.5.0 (`engram serve` is the only surface). Demo crashes at the first `recall`.
- **Fix:** pin/document a compatible engram-rs version or port to the serve API.

### MEDIUM — "Elastic hybrid search" in the operations table

- **Claim:** README table: `recall` → "Elastic hybrid search".
- **Reality:** The elastic backend here is the older standalone version (6 methods vs rapid-agent's 9, no semantic/ELSER path). Keyword search works in standalone mode; "hybrid" is aspirational. The `refactor/shared-library-extract` branch replaces it with the newer shared implementation, which narrows but does not close this gap (still no vector search).

### LOW — "agent gets smarter every time you talk to it"

Marketing-grade compounding claim; the mechanism (recall + reflect + compound
at session end) exists and runs, but "smarter" is unmeasured. Demo shows the
behavior; no benchmark backs the adverb.

### RESOLVED (previously CRITICAL) — "Timely forgetting" is now real

The deep-dive review found `_decay_confidence()` ended in `pass`. On current
`main` (Q-2 fix) decay computes age-based confidence reduction, **writes the
decayed value back** via `remember()`, and `recall_context` filters
`min_confidence=0.3`. Claim verified against code.

### RESOLVED (previously HIGH) — unbounded prompt growth

`recall_context` now enforces a `max_tokens` budget (~4 chars/token estimate,
truncates recalled lines). Token management claim verified.

## Verified claims

- Persistent memory across sessions (engram backend modulo the CRITICAL above; standalone Elastic keyword mode). ✓/⚠
- Confidence decay / timely forgetting. ✓
- Token-budgeted recall context. ✓
- Config validation with stub key passes (`DASHSCOPE_API_KEY=stub` → no issues, demo reaches the LLM-call stage). ✓
