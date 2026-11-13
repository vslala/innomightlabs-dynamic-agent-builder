# LLD: What an agent turn costs, and three ways to cut it

| Field | Value |
| --- | --- |
| Status | 🚧 In progress (all three phases built and tested locally; deploy and the measured re-run pending) |
| Owner | InnomightLabs API |
| Last reviewed | 2026-11-13, against the working tree (`main`) |
| Depends on | [LLD-llm-providers-and-image-models.md](LLD-llm-providers-and-image-models.md) (one `Provider` per vendor, the shared `wire/` formats), [api/docs/LLD-parallel-actions.md](../api/docs/LLD-parallel-actions.md) (batching, the larger design phase 3 stays inside) |

> **Summary:** Each model call in a turn re-sends the whole conversation so far, so a long tool run pays for its early context once per call. Three changes, in the order they pay off. **1. Prompt caching:** every call names its conversation (`cache_key`), each vendor reuses what it already read, and the cache reads and writes are recorded, so a run's cost shows in the logs and the usage buckets. **2. A tool index for MCP:** `list_mcp_tools` lists names and one-line summaries, not every schema, when a connector's schemas are large. The agent loads the schemas it needs, and the tools the agent used recently start the next turn already loaded, as skills already do. **3. Batched reads:** the Responses providers may return several tool calls in one response, so ten independent reads cost one model call, not ten.

Paths are relative to `api/` unless marked otherwise.

## Implementation notes

- **Phase 1 (built).**
  - **Contract.** `LLMProvider.stream_response` takes a keyword `cache_key`. `LLMEvent` carries `cache_read_tokens` and `cache_write_tokens` beside `prompt_tokens`, which now counts every input token on every vendor.
  - **Wiring.** The agent loop and Krishna Mini pass the conversation id. One-off calls (dream, compaction, vision, smart suggestions) pass nothing.
  - **Bedrock request side not built.** Converse needs explicit `cachePoint` blocks, older models reject them, and no Bedrock agent runs tool-heavy turns today. The usage side is built, so Bedrock's implicit cache hits are counted.
- **Phase 1b (built after review): a prompt that reads the same.** The system prompt opened with "Current date and time" to the minute. A new turn and every memory-write refresh therefore changed the prompt's first lines, and the whole history after them missed the cache. Three changes:
  - **The time moved onto the messages.** Each user message now starts with the time it was sent, from its own `created_at` (`conversation_strategy.sent_at`, `[Sent Friday, November 13, 2026 at 01:37 PM UTC]`), so it reads the same on every later call. `identity.j2` says once that the latest one is the current time.
  - **Replies stay unstamped.** A model shown timestamped replies starts writing them.
  - **Core memory moved last.** In Krishna MemGPT's prompt it now follows the tool sections: what tools change goes last, so a memory write re-reads only memory and the history. Ila's draft section was already last.
  - **Still a cache breaker.** `FixedWindowStrategy` drops the oldest messages once a conversation passes its word limit, which changes the start of the history on every turn after that. Not changed here.
- **Phase 2 (built).**
  - **Shared search.** The keyword search and `summarize` moved from `src/skills/disclosure.py` to `src/common/keyword_search.py` (`rank`, `summarize`), used by both disclosures.
  - **Listing and cache.** `MCPConnectorService._offered_tools` holds the cached server list and the caller filter. `list_runtime_tools` takes `tool_names` and `query`, and the tool's `tools` argument reaches it as `tool_names`.
  - **Recent tools.** `recent_runtime_tools` builds the working set; `KrishnaMemGPT._recent_mcp_tools` loads it into `state.recent_mcp_tools`, and any failure leaves it empty.
  - **Tests.** The cache is cleared between tests (`tests/conftest.py`, `fresh_mcp_tool_lists`).
- **Phase 3 (built).** `parallel_tool_calls: True` in `responses_body`, and `ANCHOR_BATCH` in `krishna_memgpt_system_prompt.j2`. Calls still run one after another; running read-only calls concurrently stays with [LLD-parallel-actions.md](../api/docs/LLD-parallel-actions.md) Part A.
- **Phase 3 regression, fixed (2026-11-13).** The first deployed Grok run with batching sent four `load_skill` calls in one response, and all four reached the tools with `{}`. Only the streamed deltas were read for arguments, and arguments that couldn't be read were silently turned into `{}`, so the agent got "skill_id Field required" instead of the truth. The fix has three parts:
  - **Assembler.** `src/llm/wire/responses_calls.py` (`FunctionCallAssembler`) builds each call from whichever events carry its arguments, by authority: the finished item (`output_item.done`, or the completed response's `output`), then `function_call_arguments.done`, then the deltas. It matches events by item id or, without one, by output index, emits each call once, and logs which event carried the arguments.
  - **Handler table.** `stream_chat` reads events through `ResponseStream`, one handler per event type.
  - **Unreadable arguments.** `LLMEvent.tool_call` and `read_tool_arguments` (`src/llm/chat.py`) are the one rule for Responses, Bedrock and Ollama: an object or nothing is read; anything else sets `tool_input_error`. The loop then doesn't run the call and tells the model why (`unreadable_arguments`).

## 1. The problem, measured

Run `2e611287` of the daily social post automation (agent `8df092ee`, Grok `grok-4.7`), on 2026-11-13:

| | This run | The run before (`589a57dd`) |
| --- | --- | --- |
| Model calls / tool calls | 51 / 50 | 17 / 16 |
| Wall time | 1,507 s (1,274 s waiting on the model) | 232 s |
| Prompt tokens | 9.01 M | 2.27 M |
| Completion tokens | 88.7 k | 10.6 k |

Input is 99% of the tokens, so input price decides the bill. Where it went:

1. **MCP schemas.** Two `list_mcp_tools` results (130 k and 251 k characters, about 95 k tokens) stayed in the context for the rest of the turn and were re-read on about 48 calls: roughly 4.5 M tokens. The agent used five of the tools listed.
2. **One call per read.** Ten `get_commit` calls ran one model call apiece, each re-reading about 105 k tokens.
3. **Full price.** We sent no cache key and recorded no cached tokens. xAI routes a call without a key to any server, so its earlier prefix was most likely not found, and the run paid full price for all 9 M tokens.

Tool results are never removed within a turn (`_Turn.run_tools` appends them whole), and the loop's only edit to earlier messages is the moving continuation nudge (`_Turn.nudge`).

## 2. Phase 1: prompt caching (built)

### 2.1 What a cache does and doesn't do

A cache doesn't shrink the context: the model still reads every token. The vendor keeps its processed state for a prefix it has seen and, when the next call starts with the same prefix, skips processing it and bills those tokens at a fraction of the price. In a tool loop, call *k* starts with everything call *k−1* sent, so almost all of a long turn's input can be cache hits.

### 2.2 One contract for every vendor

```python
# src/llm/chat.py
class LLMEvent:
    #: Every input token of the call, however the vendor splits them: it reports cache hits and writes apart.
    prompt_tokens: int = 0
    completion_tokens: int = 0
    #: The parts of `prompt_tokens` the vendor read from its prompt cache, and wrote to it.
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

class LLMProvider(ABC):
    async def stream_response(self, messages, credentials, tools=None, model=None, *, cache_key=None): ...
```

`cache_key` names the conversation a call continues. A one-off call sends none, so a vendor that charges for cache writes (Anthropic) doesn't charge for a write that nothing will read.

Each vendor maps the contract onto its own API, checked against its docs on 2026-11-13:

| Vendor | Request | Usage | Where |
| --- | --- | --- | --- |
| OpenAI API, ChatGPT sign-in (Codex), xAI | `prompt_cache_key` in the Responses body. Codex also keeps one `session-id` per conversation, as the Codex CLI does | `input_tokens` includes the cache. `input_tokens_details.cached_tokens` and `cache_write_tokens` break it out | `src/llm/wire/responses.py` (`responses_body`, `usage_event`), `openai/chat.py` (`codex_headers`) |
| Anthropic | `cache_control` on the newest message's last two blocks (section 2.3) | `input_tokens` excludes `cache_read_input_tokens` and `cache_creation_input_tokens`. We add them back | `anthropic/chat.py` (`mark_cache_breakpoints`, `usage_event`) |
| Bedrock (Converse) | Not sent (see the implementation notes) | `inputTokens` excludes `cacheReadInputTokens` and `cacheWriteInputTokens`. We add them back | `bedrock/chat.py` (`usage_event`) |
| Gemini | Nothing: implicit caching is on for 2.5 and later | `cached_content_token_count`, inside `prompt_token_count` | `gemini/chat.py` |
| Ollama | Nothing (local) | No cache fields | none |

`ModelFallbackProvider` passes the key through, so a substitute model continues the same conversation's cache.

### 2.3 Anthropic and the moving nudge

Anthropic caches only up to blocks marked `cache_control`. A later call looks back up to 20 blocks from its own marks for a prefix an earlier call wrote. The loop's continuation instruction rides as the last block of the newest tool results and moves on every call (`_Turn.nudge`), so a prefix ending with it is never sent again. Marking only the last block would write a cache on every call and never read one. `mark_cache_breakpoints` marks the last two blocks. The second-to-last is the newest tool result, which the next call still sends, and a loop call adds two blocks, well inside the look-back.

### 2.4 Recording

- **Buckets.** `TokenUsageRepository.increment_usage` adds `cache_read_tokens` and `cache_write_tokens` to the day, month and year buckets, beside `prompt_tokens`. `TokenUsagePoint` serves them.
- **Logs.** Each model call's log line ends with its tokens, and the turn ends with a total:

```text
Agent turn conversation=c5dcdd7c-… calls=51 prompt_tokens=9012345 cache_read_tokens=8601234 cache_write_tokens=0 completion_tokens=88712
```

`TokenTally` (`src/agents/agentic_loop.py`) sums the calls. The SPA's usage chart doesn't show the cache counts yet.

### 2.5 Validation

1. Re-run the same automation after the deploy, and read its `Agent turn` line.
2. `cache_read_tokens / prompt_tokens` is the cache's share.
3. Expect most of the input to be cache hits on Grok and OpenAI. Zero means the key isn't reaching the vendor, or the prefix changes between calls.

## 3. Phase 2: a tool index for MCP, and the tools the agent used

### 3.1 Follow the skills

Skills already solve this for their actions (`src/skills/disclosure.py`, `SkillRuntimeService.recent_actions`):

- **Index first.** `load_skill` on a large skill returns an action index: names and summaries, no schemas.
- **Load on demand.** `load_skill(skill_id, actions=[...])` or `query="..."` returns the chosen schemas.
- **Remembered working set.** The actions used recently are rendered with their schemas into the system prompt ("Loaded actions"), so the agent calls them without loading again.

MCP gets the same three, with the same words in the tool contract. The `call_mcp_tool` indirection stays, as `execute_skill_action` does for skills.

### 3.2 `list_mcp_tools`

```python
# src/connectors/mcp/runtime_tools.py
"properties": {
    "mcp_id": {"type": "string", "description": "MCP connector id. Omit to list every enabled connector."},
    "tools": {"type": "array", "items": {"type": "string"},
              "description": "Exact tool names whose input schemas you need."},
    "query": {"type": "string", "description": "Words describing the tool you need; returns the best matches."},
}
```

What each connector's entry holds, decided by one strategy list (`src/connectors/mcp/disclosure.py`, the same shape as the skills' `DISCLOSURES`):

| Asked | Returned |
| --- | --- |
| `tools=[...]` | Those tools whole. `unknown_tools` and `suggestions` for names it doesn't have |
| `query="..."` | The best five matches, whole |
| Neither, and the connector's schemas fit `INLINE_SCHEMA_CHARS` (8,000 characters) | Every tool whole, as today: a small connector costs no extra call |
| Neither, larger | `tool_index`: `[{name, summary}]`, and a note to load the tools it needs |

The skills' keyword scoring and `summarize` move to one shared helper that both disclosures use, so there is one search and one summary rule.

### 3.3 The listing, cached

`MCPConnectorService.list_runtime_tools` asks the server for its tools on every call. A turn may now list a connector two or three times (the index, then the tools), and every turn of a daily automation lists it again. An in-process cache keeps each connection's raw `tools/list` for `MCP_TOOL_LIST_TTL_SECONDS` (5 minutes), keyed by `mcp_id`. The caller's filter (`link.offered_tools`) still runs on every read, so caching never widens what a caller sees.

### 3.4 The tools the agent used recently

Every MCP call is already recorded per agent, newest first (`MCPCall`, `pk = Agent#{agent_id}#MCPCalls`, 90-day TTL). At the start of a turn:

1. `MCPUsageRepository.recent_tools(agent_id)` reads the newest successful calls and keeps up to `RECENT_TOOL_LIMIT` (8) distinct `(mcp_id, tool_name)` pairs.
2. The turn looks their schemas up through `list_runtime_tools` for this caller (cached, filtered), so a tool the caller may not use, or one the server dropped, falls out by itself.
3. `state.recent_mcp_tools` is rendered into `mcp_connectors.j2` as "Loaded tools", with each tool's schema. The rules say: call these with `call_mcp_tool` directly, and list only for anything else.

The working set is per agent, not per conversation, because each automation run is a new conversation. That is the case that pays most: a daily run starts with yesterday's tools loaded and makes no discovery calls. The schemas sit in the system prompt, which every call of the turn sends unchanged, so phase 1's cache serves them after the first call.

### 3.5 Expected effect on the measured run

| | Today | With the index and the working set |
| --- | --- | --- |
| Schemas carried | ~95 k tokens | ~3–5 k (five loaded tools, or a short index) |
| Re-read over ~48 calls | ~4.5 M tokens | ~0.2 M |
| Discovery calls | 2 listings | 0, once the working set holds the tools |

## 4. Phase 3: several reads in one model call

The Responses body sends `parallel_tool_calls: False`, set in June 2026 because the loop then ran one call per iteration and the tools have side effects. The loop has since learned batches (`_Turn.run_tools`):
- It runs a response's calls one after another, in the model's order.
- It skips the rest of a batch once a call stops for consent (`SKIPPED_FOR_CONSENT`).
- It asks for one prompt refresh after a batch that wrote memory.

So the flag can go to `True`, and order and side effects stay as safe as they are on Anthropic, which allows parallel calls by default. Running the calls one after another still saves the round trips, which is where the tokens go. Running read-only calls concurrently saves time too, and is Part A of [LLD-parallel-actions.md](../api/docs/LLD-parallel-actions.md). It is not needed for the cost.

The tool rules gain one line: "When you need several reads that don't depend on each other, ask for them together in one response."

On the measured run, the ten `get_commit` calls become one model call, saving about 9 × 105 k ≈ 0.95 M tokens.

## 5. Rollout

1. **Phase 1.** Deploy, re-run the automation, read the `Agent turn` line (section 2.5).
2. **Phase 2.** The index only appears for connectors over `INLINE_SCHEMA_CHARS`, so small connectors behave as today. Watch the run inspector for `list_mcp_tools` calls followed by a `tools=[...]` load.
3. **Phase 3.** One flag. If a vendor misbehaves with batches, turning it back off is a one-line change.

## 6. Alternatives considered

- **MCP tools as first-class tool definitions** (the model calls `github__get_commit` directly). The provider would check the arguments, but every tool definition sits in `tools`, which can't change mid-turn without breaking the cache, and it diverges from how skills work. Kept for later.
- **Removing old tool results from the context.** It would cut tokens, but it edits earlier history, which defeats the cache, and the model loses what it read. Revisit once phases 1–3 are measured.
