# Contributing to Agent Architectures

This folder contains **agent architectures** (e.g. `krishna_memgpt`) and the supporting plumbing that makes them maintainable at scale.

The goal of this document is to help you make changes **without turning a working architecture into a monolith**.

## Philosophy (read this first)

### 1) Keep architectures "waterfall"
Architecture entrypoints (e.g. `KrishnaMemGPTArchitecture.handle_message`) should read like a table of contents:

1. Preflight (load state)
2. Build system prompt
3. Build conversation context
4. Run the agentic loop
5. Persist outputs

If you find yourself adding branching logic or long blocks of formatting to the entrypoint, it probably belongs in a seam below.

### 2) Prefer typed state over cross-module "re-reads"
We aim for **one load per turn** for shared data (memory snapshot, enabled skills, KB ids, credentials). Then we render from that snapshot.

### 3) One responsibility per seam
Changes should be made at the appropriate seam. This reduces merge conflicts and keeps reasoning local.

---

## The seams (where to make changes)

### A) Prompt & context building (preferred for most changes)
**Files:**
- `krishna_memgpt_prompt.py`
- `krishna_memgpt_prompt_loaders.py`
- `../../agents/prompt_pipeline.py`

**Use this seam when:**
- You want to add/remove/reorder system-prompt sections
- You want to change wording/instructions
- You want to add new context blocks (skills index, KB instructions, policy, diagnostics)

**How:**
1. Create or update a loader in `krishna_memgpt_prompt_loaders.py`.
2. Declare its contract explicitly:
   - `requires = (...)` for *fatal* inputs
   - `optional_requires = (...)` for optional sections
3. If the loader needs new inputs, add them to `PromptRuntime` and populate them in the orchestrator.

**Rule:** loaders should be renderers. Avoid network calls and DB reads inside loaders.

### B) Turn orchestration (keep it thin)
**File:** `krishna_memgpt.py`

**Use this seam when:**
- You need to change the order of turn steps
- You need to add a new preflight step to populate runtime state
- You need to change how we rebuild/refresh the system prompt

**Rule:** this file should glue together:
- state preparation
- prompt building
- context building
- agentic loop
- persistence

### C) Agentic loop mechanics
**File:** `../../agents/agentic_loop.py`

**Use this seam when:**
- You want to change how tool calls are batched
- You want to change how we append toolUse/toolResult blocks into context
- You want to change stop conditions or iteration limits

### D) Tool routing + tool error policy
**File:** `../../agents/tool_execution.py`

**Use this seam when:**
- You add a new tool category (native vs skills vs other)
- You want to standardize tool error outputs
- You want to mark prompt refresh conditions (e.g. memory write tools)

### E) Per-turn runtime state
**File:** `../../agents/runtime_state.py`

**Use this seam when:**
- You need to add one more piece of state that multiple components need

---

## Robustness rules

### 1) Prompt refresh on memory mutation
If a tool mutates core memory, the model must not operate on stale memory.

- Mark dirty in `tool_execution.py`
- Trigger refresh event in `agentic_loop.py`
- Rebuild + replace system prompt in `krishna_memgpt.py`

### 2) Error handling
- Tool failures should be returned as tool results (so the next loop iteration sees the failure).
- Fatal preflight failures should *not* call the LLM; they should return a clear SSE error to the UI.

---

## How to make a change (recommended procedure)

1. Create a branch from `main`
2. Make one small commit per step (plumbing → behavior → cleanup)
3. Run backend tests:
   ```bash
   cd api
   uv run pytest
   ```
4. In PR description, state:
   - which seam you changed
   - what new runtime fields/loaders were introduced
   - whether output formatting changed

---

## Common examples

### Example: add a new prompt section
1. Add `MySectionLoader(PromptLoaderBase)`
2. Add it to the pipeline list in `krishna_memgpt_prompt.py`
3. If it needs data, add it to `PromptRuntime` and populate it once in `krishna_memgpt.py`

### Example: add a new tool that updates memory
1. Implement tool logic (native tool handler)
2. Add tool name to the "memory write" set in `tool_execution.py` so prompt is refreshed
3. Add/adjust tests

---

## Non-goals

- We are not trying to make everything generic immediately.
- We prefer incremental refactors with green tests over large rewrites.
