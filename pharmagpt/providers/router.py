"""
pharmagpt/providers/router.py — AI provider orchestration layer.

Additive only. This module does not touch pharmagpt/state.py, and every
existing route/service keeps doing `from pharmagpt.state import
gemini_client` exactly as before — unchanged behavior, unchanged API
contracts. This module is a new, opt-in entry point for call sites that want
automatic per-task provider selection instead of hardcoding Gemini.

Routing
-------
TaskIntent buckets into two groups:

  Conversational / reasoning -> DEFAULT_CHAT_PROVIDER (default: "nemotron")
      CHAT, GENERAL_QA, SUMMARY, SEARCH, UNKNOWN

  Structured document generation -> DEFAULT_DOCUMENT_PROVIDER (default: "gemini")
      URS, DQ, IQ, OQ, PQ, SAT, FAT, VALIDATION_PLAN, VALIDATION_SUMMARY,
      RISK_ASSESSMENT, FMEA, CAPA, CHANGE_CONTROL, SOP, FACILITY_URS

Configuration (.env, all optional, see pharmagpt/config.py)
-------------------------------------------------------------------
    DEFAULT_CHAT_PROVIDER=nemotron
    DEFAULT_DOCUMENT_PROVIDER=gemini
    ENABLE_FALLBACK=true

Router API
----------
    get_client(intent) -> duck-typed client (.models.generate_content(...) /
        .models.generate_content_stream(...)), same contract as
        pharmagpt.state.gemini_client. No retry/fallback — for callers that
        want the selected client and will manage the call themselves.

    generate_content(intent, contents=..., config=...) -> response
    generate_content_stream(intent, contents=..., config=...) -> generator
        Fully orchestrated: retries the selected provider once, then falls
        back to the other provider (if ENABLE_FALLBACK and one is
        registered+configured), logging every attempt. Raises
        ProviderCallError (sanitized message; original exception chained via
        __cause__ for logs/debugging only) if every attempt fails.

Fallback
--------
Selected provider fails -> retry once (same provider) -> still failing ->
one attempt on the other provider. Never exposes upstream error bodies to
the caller (google.genai / NVIDIA response text stays in logs only).

Future providers (Claude, OpenAI, OpenRouter, Ollama, Azure OpenAI, ...)
-------------------------------------------------------------------------
1. Create the provider class (duck-typed to .models.generate_content() /
   .models.generate_content_stream(), see providers/nemotron_client.py).
2. register_provider("name", builder_fn, model="...") — one call, anywhere
   imported before first use; _register_default_providers() below is the
   worked example for gemini/nemotron.
3. Point a routing bucket (_CHAT_INTENTS / _DOCUMENT_INTENTS) or
   DEFAULT_CHAT_PROVIDER / DEFAULT_DOCUMENT_PROVIDER at it.
No existing routing, business logic, or call site changes required.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Callable

from pharmagpt.config import (
    DEFAULT_CHAT_PROVIDER,
    DEFAULT_DOCUMENT_PROVIDER,
    ENABLE_FALLBACK,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    NVIDIA_API_KEY,
    NVIDIA_MODEL,
)
from pharmagpt.providers.factory import ProviderConfigError, get_ai_client

logger = logging.getLogger(__name__)


class TaskIntent(str, Enum):
    CHAT = "chat"
    SEARCH = "search"
    SUMMARY = "summary"
    URS = "urs"
    DQ = "dq"
    IQ = "iq"
    OQ = "oq"
    PQ = "pq"
    SAT = "sat"
    FAT = "fat"
    VALIDATION_PLAN = "validation_plan"
    VALIDATION_SUMMARY = "validation_summary"
    RISK_ASSESSMENT = "risk_assessment"
    FMEA = "fmea"
    CAPA = "capa"
    CHANGE_CONTROL = "change_control"
    SOP = "sop"
    FACILITY_URS = "facility_urs"
    GENERAL_QA = "general_qa"
    UNKNOWN = "unknown"


class ProviderCallError(RuntimeError):
    """Raised when every attempt (primary retry + fallback) fails. The
    message is intentionally generic — never includes the upstream provider's
    response body — so callers can surface str(exc) straight to a user. The
    original exception is chained via __cause__ for logs/debugging only."""


_CHAT_INTENTS = {
    TaskIntent.CHAT,
    TaskIntent.GENERAL_QA,
    TaskIntent.SUMMARY,
    TaskIntent.SEARCH,
}

_DOCUMENT_INTENTS = {
    TaskIntent.URS,
    TaskIntent.DQ,
    TaskIntent.IQ,
    TaskIntent.OQ,
    TaskIntent.PQ,
    TaskIntent.SAT,
    TaskIntent.FAT,
    TaskIntent.VALIDATION_PLAN,
    TaskIntent.VALIDATION_SUMMARY,
    TaskIntent.RISK_ASSESSMENT,
    TaskIntent.FMEA,
    TaskIntent.CAPA,
    TaskIntent.CHANGE_CONTROL,
    TaskIntent.SOP,
    TaskIntent.FACILITY_URS,
}

# The only two providers with a defined opposite today. A provider added via
# register_provider() without an entry here simply gets no fallback (skipped,
# logged) rather than an error — see _fallback_provider().
_OPPOSITE_PROVIDER = {"nemotron": "gemini", "gemini": "nemotron"}

ProviderBuilder = Callable[[], Any]

_PROVIDER_BUILDERS: dict[str, ProviderBuilder] = {}
_PROVIDER_MODELS: dict[str, str | None] = {}
_CLIENT_CACHE: dict[str, Any] = {}


def register_provider(name: str, builder: ProviderBuilder, *, model: str | None = None) -> None:
    """Register a provider under `name`. `builder` is a zero-arg callable
    returning a client duck-typed to .models.generate_content() /
    .models.generate_content_stream() (see providers/nemotron_client.py).
    Builders are called lazily and cached — an unconfigured/unused provider
    (e.g. no NVIDIA_API_KEY when only Gemini is routed to) never raises."""
    _PROVIDER_BUILDERS[name] = builder
    _PROVIDER_MODELS[name] = model
    _CLIENT_CACHE.pop(name, None)


def _register_default_providers() -> None:
    register_provider(
        "gemini",
        lambda: get_ai_client("gemini", GEMINI_API_KEY, None, None),
        model=GEMINI_MODEL,
    )
    register_provider(
        "nemotron",
        lambda: get_ai_client("nemotron", None, NVIDIA_API_KEY, NVIDIA_MODEL),
        model=NVIDIA_MODEL,
    )


_register_default_providers()


def _provider_for_intent(intent: TaskIntent) -> str:
    if intent in _DOCUMENT_INTENTS:
        return DEFAULT_DOCUMENT_PROVIDER
    return DEFAULT_CHAT_PROVIDER


def _fallback_provider(primary: str) -> str | None:
    candidate = _OPPOSITE_PROVIDER.get(primary)
    if candidate is None or candidate == primary or candidate not in _PROVIDER_BUILDERS:
        return None
    return candidate


def _build_client(provider: str):
    if provider not in _CLIENT_CACHE:
        builder = _PROVIDER_BUILDERS.get(provider)
        if builder is None:
            raise ProviderConfigError(f"Unknown AI provider '{provider}' — not registered with the router.")
        _CLIENT_CACHE[provider] = builder()
    return _CLIENT_CACHE[provider]


def get_client(intent: TaskIntent):
    """Return the client selected for `intent`. No retry/fallback — use
    generate_content()/generate_content_stream() for the orchestrated path."""
    return _build_client(_provider_for_intent(intent))


def _log_call(
    *,
    intent: TaskIntent,
    provider: str,
    model: str | None,
    elapsed: float,
    success: bool,
    fallback_used: bool,
    prompt_tokens=None,
    completion_tokens=None,
    reason: str | None = None,
) -> None:
    # Never logs prompt/response text (GMP/regulated content) — metadata only,
    # same restraint as providers/nemotron_client.py's own request/response logging.
    logger.info(
        "ai_router_call intent=%s provider=%s model=%s latency_ms=%.0f success=%s "
        "fallback_used=%s prompt_tokens=%s completion_tokens=%s%s",
        intent.value,
        provider,
        model,
        elapsed * 1000,
        success,
        fallback_used,
        prompt_tokens if prompt_tokens is not None else "n/a",
        completion_tokens if completion_tokens is not None else "n/a",
        f" reason={reason}" if reason else "",
    )


def _provider_order(intent: TaskIntent) -> list[str]:
    primary = _provider_for_intent(intent)
    order = [primary]
    if ENABLE_FALLBACK:
        fallback = _fallback_provider(primary)
        if fallback:
            order.append(fallback)
    return order


def generate_content(intent: TaskIntent, *, contents, config=None, **kwargs):
    """Orchestrated, non-streaming call: selected provider, retry once, then
    fallback provider (one attempt), with structured logging at every step."""
    return _run_with_fallback(
        intent,
        method="generate_content",
        contents=contents,
        config=config,
        **kwargs,
    )


def generate_content_stream(intent: TaskIntent, *, contents, config=None, **kwargs):
    """Orchestrated streaming call. Retry/fallback only cover the attempt to
    *start* the stream — once the first chunk has been yielded to the
    caller, a mid-stream failure propagates directly rather than restarting
    (restarting after partial output would duplicate content already
    delivered to the caller)."""
    order = _provider_order(intent)
    last_exc: Exception | None = None
    fallback_used = False

    for provider in order:
        attempts = 2 if not fallback_used else 1
        for _ in range(attempts):
            model = _PROVIDER_MODELS.get(provider)
            start = time.perf_counter()
            try:
                client = _build_client(provider)
                stream = client.models.generate_content_stream(
                    model=model, contents=contents, config=config, **kwargs
                )
                first = next(stream)
            except StopIteration:
                elapsed = time.perf_counter() - start
                _log_call(
                    intent=intent, provider=provider, model=model, elapsed=elapsed,
                    success=True, fallback_used=fallback_used,
                )
                return
            except Exception as exc:  # noqa: BLE001 - deliberately broad, see module docstring
                elapsed = time.perf_counter() - start
                _log_call(
                    intent=intent, provider=provider, model=model, elapsed=elapsed,
                    success=False, fallback_used=fallback_used, reason=exc.__class__.__name__,
                )
                last_exc = exc
                continue

            elapsed = time.perf_counter() - start
            _log_call(
                intent=intent, provider=provider, model=model, elapsed=elapsed,
                success=True, fallback_used=fallback_used,
            )

            def _chunks(first_chunk=first, rest=stream):
                yield first_chunk
                yield from rest

            return _chunks()
        fallback_used = True

    raise ProviderCallError(
        f"AI request failed for intent={intent.value} after retry and fallback."
    ) from last_exc


def _run_with_fallback(intent: TaskIntent, *, method: str, contents, config, **kwargs):
    order = _provider_order(intent)
    last_exc: Exception | None = None
    fallback_used = False

    for provider in order:
        attempts = 2 if not fallback_used else 1
        for _ in range(attempts):
            model = _PROVIDER_MODELS.get(provider)
            start = time.perf_counter()
            try:
                client = _build_client(provider)
                response = getattr(client.models, method)(
                    model=model, contents=contents, config=config, **kwargs
                )
            except Exception as exc:  # noqa: BLE001 - deliberately broad, see module docstring
                elapsed = time.perf_counter() - start
                _log_call(
                    intent=intent, provider=provider, model=model, elapsed=elapsed,
                    success=False, fallback_used=fallback_used, reason=exc.__class__.__name__,
                )
                last_exc = exc
                continue

            elapsed = time.perf_counter() - start
            usage = getattr(response, "usage_metadata", None)
            _log_call(
                intent=intent, provider=provider, model=model, elapsed=elapsed,
                success=True, fallback_used=fallback_used,
                prompt_tokens=getattr(usage, "prompt_token_count", None),
                completion_tokens=getattr(usage, "candidates_token_count", None),
            )
            return response
        fallback_used = True

    raise ProviderCallError(
        f"AI request failed for intent={intent.value} after retry and fallback."
    ) from last_exc
