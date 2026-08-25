"""
pharmagpt/providers/router.py — AI provider orchestration layer.

Stage 1 (AI Gateway stabilization): this module is now production-connected
— routes/chat.py calls generate_content_stream() below instead of the raw
pharmagpt.state.gemini_client singleton. Every other existing route/service
still does `from pharmagpt.state import gemini_client` exactly as before —
unchanged behavior, unchanged API contracts — until migrated in a later
stage (see docs/AI_PROVIDER_ROUTER.md for the full call-site inventory).

Routing
-------
TaskIntent buckets into two groups:

  Conversational / reasoning -> DEFAULT_CHAT_PROVIDER (default: "gemini")
      CHAT, GENERAL_QA, SUMMARY, SEARCH, UNKNOWN

  Structured document generation -> DEFAULT_DOCUMENT_PROVIDER (default: "gemini")
      URS, DQ, IQ, OQ, PQ, SAT, FAT, VALIDATION_PLAN, VALIDATION_SUMMARY,
      RISK_ASSESSMENT, FMEA, CAPA, CHANGE_CONTROL, SOP, FACILITY_URS

Configuration (.env, all optional, see pharmagpt/config.py)
-------------------------------------------------------------------
    DEFAULT_CHAT_PROVIDER=gemini
    DEFAULT_DOCUMENT_PROVIDER=gemini
    ENABLE_FALLBACK=true
    PROVIDER_QUOTA_COOLDOWN_SECONDS=60

Router API
----------
    get_client(intent) -> duck-typed client (.models.generate_content(...) /
        .models.generate_content_stream(...)), same contract as
        pharmagpt.state.gemini_client. No retry/fallback/cooldown — for
        callers that want the selected client and will manage the call
        themselves.

    generate_content(intent, contents=..., config=...) -> response
    generate_content_stream(intent, contents=..., config=...) -> generator
        Fully orchestrated: classifies every failure (see FailureCategory
        below), applies bounded same-provider retry only where retrying can
        plausibly help, skips a provider currently in quota cooldown, and
        falls back to the other provider where the failure category makes
        that a sensible response. Raises ProviderCallError (sanitized
        message; original exception chained via __cause__ for logs/
        debugging only) if every attempt fails.

Failure classification
-----------------------
Every exception raised by a provider client is classified into one of six
categories before any retry/fallback decision is made:

    TRANSIENT       Network error, provider 5xx. Retrying now can plausibly
                     succeed. Bounded same-provider retry, then fallback.
    QUOTA            429 / RESOURCE_EXHAUSTED / rate-limit. Retrying the
                     same provider immediately cannot succeed and only
                     burns further into an already-exhausted budget — no
                     retry, straight to fallback, and the provider is put
                     into cooldown (PROVIDER_QUOTA_COOLDOWN_SECONDS) so
                     later requests don't repeat the same failed call.
    AUTHENTICATION   401/403, or the provider was never configured for this
                     deployment (ProviderConfigError — e.g. missing API
                     key). Retrying the same provider is pointless (the key
                     won't become valid on attempt 2), but the other
                     provider may be perfectly healthy — no retry, but
                     still falls back.
    MODEL            Malformed/invalid-request-shaped 4xx not otherwise
                     classified. Bounded same-provider retry (mirrors
                     services/urs_generation_job.py's existing treatment of
                     malformed output), then fallback.
    SAFETY           Content-safety rejection. This is a property of the
                     content, not the provider — trying a different
                     provider to route around a safety rejection is not a
                     defensible pattern for a pharma compliance product.
                     No retry, no fallback, fails immediately.
    APPLICATION      A bug in our own request construction (TypeError,
                     KeyError, AttributeError, IndexError). Identical
                     failure would occur against any provider — no retry,
                     no fallback, fails immediately and loudly.

Any exception type not recognized above defaults to TRANSIENT (retry once,
then fallback) — a cautious default for an unknown failure mode, not a
silent swallow.

Circuit breaker / cooldown
---------------------------
A QUOTA classification puts that provider into an in-memory, per-process
cooldown for PROVIDER_QUOTA_COOLDOWN_SECONDS. While a provider is cooling
down, generate_content()/generate_content_stream() skip it entirely — no
call is made, no retry is wasted rediscovering the same 429 — and go
straight to the fallback provider (if fallback-eligible and registered).
Cooldown state is per-provider, shared across all intents and requests in
the process, and resets on process restart.

Future providers (Mistral, Groq, Claude, OpenAI, Azure OpenAI, ...)
-------------------------------------------------------------------------
Not added in Stage 1 by design. When a future stage adds one:
1. Create the provider class (duck-typed to .models.generate_content() /
   .models.generate_content_stream(), see providers/nemotron_client.py).
2. register_provider("name", builder_fn, model="...") — one call, anywhere
   imported before first use; _register_default_providers() below is the
   worked example for gemini/nemotron.
3. Point a routing bucket (_CHAT_INTENTS / _DOCUMENT_INTENTS) or
   DEFAULT_CHAT_PROVIDER / DEFAULT_DOCUMENT_PROVIDER at it, and/or add it to
   _OPPOSITE_PROVIDER if it should participate in two-way fallback (today's
   fallback graph is still the single gemini<->nemotron pair from the
   original design — extending it to more than two providers per intent is
   out of scope for Stage 1).
No existing routing, business logic, or call site changes required.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Callable

from google.genai import errors as genai_errors

from pharmagpt.config import (
    DEFAULT_CHAT_PROVIDER,
    DEFAULT_DOCUMENT_PROVIDER,
    ENABLE_FALLBACK,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    NVIDIA_API_KEY,
    NVIDIA_MODEL,
    PROVIDER_QUOTA_COOLDOWN_SECONDS,
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


class FailureCategory(str, Enum):
    TRANSIENT = "transient"
    QUOTA = "quota"
    AUTHENTICATION = "authentication"
    MODEL = "model"
    SAFETY = "safety"
    APPLICATION = "application"


class ProviderCallError(RuntimeError):
    """Raised when every attempt (retry + fallback, where applicable) fails.
    The message is intentionally generic — never includes the upstream
    provider's response body — so callers can surface str(exc) straight to
    a user. The original exception is chained via __cause__ for
    logs/debugging only."""


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

# Categories where an immediate retry against the SAME provider can
# plausibly change the outcome. Everything else either can't be fixed by
# retrying (QUOTA, AUTHENTICATION) or shouldn't be retried at all
# (SAFETY, APPLICATION).
_RETRYABLE_CATEGORIES = {FailureCategory.TRANSIENT, FailureCategory.MODEL}

# Categories where trying the OTHER provider is a sensible response to this
# provider's failure. SAFETY (a property of the content, not the provider)
# and APPLICATION (a bug in our own code, reproducible against any provider)
# are deliberately excluded — see the module docstring.
_FALLBACK_ELIGIBLE_CATEGORIES = {
    FailureCategory.TRANSIENT,
    FailureCategory.QUOTA,
    FailureCategory.AUTHENTICATION,
    FailureCategory.MODEL,
}

# 1 initial attempt + 1 bounded retry, for retryable categories only.
_MAX_ATTEMPTS_PER_PROVIDER = 2

_QUOTA_MARKERS = ("resource_exhausted", "quota", "rate limit", "too many requests")
_AUTH_MARKERS = ("unauthenticated", "unauthorized", "invalid api key", "invalid_api_key", "permission denied")
_SAFETY_MARKERS = ("safety", "blocked", "recitation", "content_filter", "content filter")

ProviderBuilder = Callable[[], Any]

_PROVIDER_BUILDERS: dict[str, ProviderBuilder] = {}
_PROVIDER_MODELS: dict[str, str | None] = {}
_CLIENT_CACHE: dict[str, Any] = {}

# provider name -> monotonic time.monotonic() timestamp the cooldown ends.
# Populated only by a QUOTA classification; see _start_cooldown()/_in_cooldown().
_provider_cooldown_until: dict[str, float] = {}


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
    """Return the client selected for `intent`. No retry/fallback/cooldown —
    use generate_content()/generate_content_stream() for the orchestrated
    path."""
    return _build_client(_provider_for_intent(intent))


def _classify_failure(exc: Exception) -> FailureCategory:
    """Classify a raised exception into a FailureCategory. Provider-raised
    errors (google.genai.errors.ServerError/ClientError — the shape both the
    real Gemini SDK and providers/nemotron_client.py's mimicked adapter
    raise) are classified by HTTP status code first, then by matching known
    marker text in the status/message (covers cases where a provider uses a
    4xx code generically but signals the real reason in the body — e.g.
    Gemini's RESOURCE_EXHAUSTED status on a 429). A missing/misconfigured
    provider (ProviderConfigError — e.g. no API key set for this deployment)
    is treated as AUTHENTICATION: retrying won't help, but it says nothing
    about whether the OTHER provider works, so it stays fallback-eligible.
    Anything else recognized as a bug in our own request construction
    (TypeError/KeyError/AttributeError/IndexError) is APPLICATION. Any
    unrecognized exception type defaults to TRANSIENT — a cautious "retry
    once, then fallback" response to an unknown failure mode, not a silent
    swallow."""
    if isinstance(exc, ProviderConfigError):
        return FailureCategory.AUTHENTICATION

    if isinstance(exc, genai_errors.ServerError):
        return FailureCategory.TRANSIENT

    if isinstance(exc, genai_errors.ClientError):
        code = getattr(exc, "code", None)
        text = f"{getattr(exc, 'status', '') or ''} {getattr(exc, 'message', '') or ''} {exc}".lower()
        if code == 429 or any(marker in text for marker in _QUOTA_MARKERS):
            return FailureCategory.QUOTA
        if code in (401, 403) or any(marker in text for marker in _AUTH_MARKERS):
            return FailureCategory.AUTHENTICATION
        if any(marker in text for marker in _SAFETY_MARKERS):
            return FailureCategory.SAFETY
        return FailureCategory.MODEL

    if isinstance(exc, (TypeError, KeyError, AttributeError, IndexError)):
        return FailureCategory.APPLICATION

    return FailureCategory.TRANSIENT


def _start_cooldown(provider: str) -> None:
    _provider_cooldown_until[provider] = time.monotonic() + PROVIDER_QUOTA_COOLDOWN_SECONDS
    logger.warning(
        "ai_router_cooldown_start provider=%s seconds=%s",
        provider, PROVIDER_QUOTA_COOLDOWN_SECONDS,
    )


def _in_cooldown(provider: str) -> bool:
    until = _provider_cooldown_until.get(provider)
    return until is not None and time.monotonic() < until


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
    category: FailureCategory | None = None,
) -> None:
    # Never logs prompt/response text (GMP/regulated content) — metadata only,
    # same restraint as providers/nemotron_client.py's own request/response logging.
    logger.info(
        "ai_router_call intent=%s provider=%s model=%s latency_ms=%.0f success=%s "
        "fallback_used=%s prompt_tokens=%s completion_tokens=%s%s%s",
        intent.value,
        provider,
        model,
        elapsed * 1000,
        success,
        fallback_used,
        prompt_tokens if prompt_tokens is not None else "n/a",
        completion_tokens if completion_tokens is not None else "n/a",
        f" reason={reason}" if reason else "",
        f" category={category.value}" if category else "",
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
    """Orchestrated, non-streaming call: classify -> bounded retry where
    retrying can help -> cooldown-aware fallback where falling back makes
    sense, with structured logging at every step."""
    return _run_with_fallback(
        intent,
        method="generate_content",
        contents=contents,
        config=config,
        **kwargs,
    )


def generate_content_stream(intent: TaskIntent, *, contents, config=None, **kwargs):
    """Orchestrated streaming call. Classification/retry/fallback/cooldown
    only cover the attempt to *start* the stream — once the first chunk has
    been yielded to the caller, a mid-stream failure propagates directly
    rather than restarting (restarting after partial output would duplicate
    content already delivered to the caller)."""
    order = _provider_order(intent)
    last_exc: Exception | None = None
    last_category: FailureCategory | None = None
    fallback_used = False

    for provider in order:
        if _in_cooldown(provider):
            logger.info(
                "ai_router_call intent=%s provider=%s skipped=cooldown_active fallback_used=%s",
                intent.value, provider, fallback_used,
            )
            last_exc = last_exc or ProviderCallError(
                f"provider '{provider}' is in quota cooldown"
            )
            last_category = FailureCategory.QUOTA
            fallback_used = True
            continue

        model = _PROVIDER_MODELS.get(provider)
        attempt = 0
        category: FailureCategory | None = None
        started_ok = False

        while True:
            attempt += 1
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
                # Bug fix (Stage 3): generate_content_stream() is a regular
                # function (only the inner _chunks() closure below is a
                # generator) — a bare `return` here returns None, not an
                # empty iterable, which crashes every caller's `for chunk in
                # ai_router.generate_content_stream(...)` with "'NoneType'
                # object is not iterable" whenever a provider's stream is
                # genuinely empty (zero chunks, immediate StopIteration).
                # Present since Stage 1 (equally affects routes/chat.py);
                # first caught by Stage 3's empty-output tests. Restores the
                # function's own documented "-> generator" contract — no
                # other behavior (retry/fallback/classification/cooldown)
                # changes.
                return iter(())
            except Exception as exc:  # noqa: BLE001 - classified below, see _classify_failure
                elapsed = time.perf_counter() - start
                category = _classify_failure(exc)
                _log_call(
                    intent=intent, provider=provider, model=model, elapsed=elapsed,
                    success=False, fallback_used=fallback_used,
                    reason=exc.__class__.__name__, category=category,
                )
                last_exc = exc
                last_category = category
                if category == FailureCategory.QUOTA:
                    _start_cooldown(provider)
                if category in _RETRYABLE_CATEGORIES and attempt < _MAX_ATTEMPTS_PER_PROVIDER:
                    continue
                break
            else:
                elapsed = time.perf_counter() - start
                _log_call(
                    intent=intent, provider=provider, model=model, elapsed=elapsed,
                    success=True, fallback_used=fallback_used,
                )
                started_ok = True

                def _chunks(first_chunk=first, rest=stream):
                    yield first_chunk
                    yield from rest

                return _chunks()

        if not started_ok and category not in _FALLBACK_ELIGIBLE_CATEGORIES:
            raise ProviderCallError(
                f"AI request failed for intent={intent.value} "
                f"(category={category.value}, non-retryable, no fallback attempted)."
            ) from last_exc
        fallback_used = True

    raise ProviderCallError(
        f"AI request failed for intent={intent.value} after retry and fallback "
        f"(category={last_category.value if last_category else 'unknown'})."
    ) from last_exc


def _run_with_fallback(intent: TaskIntent, *, method: str, contents, config, **kwargs):
    order = _provider_order(intent)
    last_exc: Exception | None = None
    last_category: FailureCategory | None = None
    fallback_used = False

    for provider in order:
        if _in_cooldown(provider):
            logger.info(
                "ai_router_call intent=%s provider=%s skipped=cooldown_active fallback_used=%s",
                intent.value, provider, fallback_used,
            )
            last_exc = last_exc or ProviderCallError(
                f"provider '{provider}' is in quota cooldown"
            )
            last_category = FailureCategory.QUOTA
            fallback_used = True
            continue

        model = _PROVIDER_MODELS.get(provider)
        attempt = 0
        category: FailureCategory | None = None

        while True:
            attempt += 1
            start = time.perf_counter()
            try:
                client = _build_client(provider)
                response = getattr(client.models, method)(
                    model=model, contents=contents, config=config, **kwargs
                )
            except Exception as exc:  # noqa: BLE001 - classified below, see _classify_failure
                elapsed = time.perf_counter() - start
                category = _classify_failure(exc)
                _log_call(
                    intent=intent, provider=provider, model=model, elapsed=elapsed,
                    success=False, fallback_used=fallback_used,
                    reason=exc.__class__.__name__, category=category,
                )
                last_exc = exc
                last_category = category
                if category == FailureCategory.QUOTA:
                    _start_cooldown(provider)
                if category in _RETRYABLE_CATEGORIES and attempt < _MAX_ATTEMPTS_PER_PROVIDER:
                    continue
                break
            else:
                elapsed = time.perf_counter() - start
                usage = getattr(response, "usage_metadata", None)
                _log_call(
                    intent=intent, provider=provider, model=model, elapsed=elapsed,
                    success=True, fallback_used=fallback_used,
                    prompt_tokens=getattr(usage, "prompt_token_count", None),
                    completion_tokens=getattr(usage, "candidates_token_count", None),
                )
                return response

        if category not in _FALLBACK_ELIGIBLE_CATEGORIES:
            raise ProviderCallError(
                f"AI request failed for intent={intent.value} "
                f"(category={category.value}, non-retryable, no fallback attempted)."
            ) from last_exc
        fallback_used = True

    raise ProviderCallError(
        f"AI request failed for intent={intent.value} after retry and fallback "
        f"(category={last_category.value if last_category else 'unknown'})."
    ) from last_exc
