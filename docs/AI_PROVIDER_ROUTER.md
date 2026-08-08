# AI Provider Router — Architecture Summary

Status: Implemented, additive. Does not change existing behavior.

## Problem

`pharmagpt/providers/factory.py` + `pharmagpt/state.py` select **one**
provider (`AI_PROVIDER=gemini|nemotron`) for the entire app at process
startup, exposed as the single `gemini_client` singleton every route/service
imports. That stays exactly as-is. This work adds a second, opt-in layer on
top: automatic **per-task** provider selection, so future call sites can get
Gemini for structured document generation and Nemotron for conversational
reasoning without a global switch or route-level branching.

## What was built

`pharmagpt/providers/router.py` — new file, nothing else touched except two
additive changes:

- `pharmagpt/config.py`: three new env-backed settings (`DEFAULT_CHAT_PROVIDER`,
  `DEFAULT_DOCUMENT_PROVIDER`, `ENABLE_FALLBACK`), read only by router.py.
- `.env.example`: documents the three new optional vars.

`pharmagpt/state.py`, `pharmagpt/providers/factory.py`,
`pharmagpt/providers/nemotron_client.py`, every `routes/*.py`,
`services/*.py`, and every prompt file are **unmodified**.

### TaskIntent

`TaskIntent` (str Enum) — one member per document/interaction type:
`CHAT, SEARCH, SUMMARY, URS, DQ, IQ, OQ, PQ, SAT, FAT, VALIDATION_PLAN,
VALIDATION_SUMMARY, RISK_ASSESSMENT, FMEA, CAPA, CHANGE_CONTROL, SOP,
FACILITY_URS, GENERAL_QA, UNKNOWN`.

### Routing rules

| Bucket | Intents | Provider (default) |
|---|---|---|
| Conversational / reasoning | CHAT, GENERAL_QA, SUMMARY, SEARCH, UNKNOWN | `DEFAULT_CHAT_PROVIDER` = nemotron |
| Structured document generation | URS, DQ, IQ, OQ, PQ, SAT, FAT, VALIDATION_PLAN, VALIDATION_SUMMARY, RISK_ASSESSMENT, FMEA, CAPA, CHANGE_CONTROL, SOP, FACILITY_URS | `DEFAULT_DOCUMENT_PROVIDER` = gemini |

Both are `.env`-overridable; no code change needed to flip either bucket.

### Router API

```python
from pharmagpt.providers.router import TaskIntent, get_client, generate_content, generate_content_stream

client = get_client(TaskIntent.URS)          # selected client, no retry/fallback
resp   = generate_content(TaskIntent.CHAT, contents=[...], config=...)   # orchestrated
for chunk in generate_content_stream(TaskIntent.CHAT, contents=[...]):   # orchestrated, streaming
    ...
```

`get_client(intent)` returns a client duck-typed identically to
`pharmagpt.state.gemini_client` (`.models.generate_content()` /
`.models.generate_content_stream()`) — a caller cannot tell which provider
it got. `generate_content` / `generate_content_stream` additionally own
retry + fallback + logging (below).

### Fallback

Selected provider fails (raises, including a provider misconfiguration such
as a missing API key surfaced at first use) → retry once on the same
provider → still failing → one attempt on the other provider, if
`ENABLE_FALLBACK=true` (default) and that provider is registered. All
failures raise `ProviderCallError` with a generic message; the original
exception is chained via `__cause__` for logs only — upstream response
bodies never reach the caller.

Streaming fallback covers only *starting* the stream (first chunk). Once a
chunk has reached the caller, a later mid-stream failure propagates directly
— restarting would duplicate content already delivered.

### Logging

Every attempt logs (via `logging.getLogger("pharmagpt.providers.router")`,
which already flows through `pharmagpt/logging_config.py`'s existing
`pharmagpt` handler): task intent, selected provider, selected model,
latency, success/failure, fallback-used, prompt/completion token counts when
available, and the failure's exception class name on error. Prompt/response
text is never logged (matches `providers/nemotron_client.py`'s existing
GMP-content restraint).

### Adding a new provider (Claude, OpenAI, OpenRouter, Ollama, Azure OpenAI, …)

1. Write the provider class, duck-typed to `.models.generate_content()` /
   `.models.generate_content_stream()` (see `providers/nemotron_client.py`
   for the reference implementation, including the `google.genai`
   response/error shape every existing call site expects).
2. `register_provider("name", builder_fn, model="...")` — one call.
3. Point `DEFAULT_CHAT_PROVIDER` / `DEFAULT_DOCUMENT_PROVIDER` (env) at it,
   or add it to `_OPPOSITE_PROVIDER` in router.py if it should participate
   in two-way fallback.

No routing table, business logic, prompt, or existing call-site change
required.

## Backward compatibility

- `AI_PROVIDER` and `pharmagpt.state.gemini_client` behave exactly as
  before — router.py never touches `state.py`.
- No route, service, prompt, or document generator was modified.
- All 300+ pre-existing tests pass unchanged (see `tests/test_provider_router.py`
  for the router's own unit/integration coverage: routing rules, retry,
  fallback — including builder-level misconfiguration — logging fields,
  streaming, and a direct check that `pharmagpt.state.gemini_client` is
  unaffected by importing/using the router).

## Adoption

Router usage is opt-in. Existing routes/services are unaffected until a
call site is deliberately migrated from `pharmagpt.state.gemini_client` to
`pharmagpt.providers.router.get_client(intent)` /
`generate_content(intent, ...)` — out of scope for this change.
