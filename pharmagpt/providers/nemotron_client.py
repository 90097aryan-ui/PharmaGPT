"""
pharmagpt/providers/nemotron_client.py — NVIDIA Nemotron 3 Ultra provider.

NemotronClient is a duck-typed drop-in replacement for google.genai.Client.
It exposes the same `.models.generate_content()` / `.models.generate_
content_stream()` surface that every existing call site in this codebase
(pharmagpt/state.py's `gemini_client`, and everything that imports it)
already uses — so when AI_PROVIDER=nemotron (pharmagpt/config.py), routes
and services need no changes at all: they keep calling
`gemini_client.models.generate_content(model=GEMINI_MODEL, contents=[...],
config=types.GenerateContentConfig(...))` exactly as before, and this
adapter translates that into an NVIDIA API call underneath.

Request/response translation
-----------------------------
- `contents` (list[google.genai.types.Content]) -> OpenAI-style `messages`.
  role "model" -> "assistant" (Gemini's convention; OpenAI-compatible APIs
  expect "assistant"), "user" -> "user".
- `config.system_instruction` -> a leading {"role": "system", ...} message.
- `config.temperature` / `config.max_output_tokens` -> `temperature` /
  `max_tokens`.
- `config.response_mime_type == "application/json"` -> best-effort
  `response_format={"type": "json_object"}`. `config.response_schema`
  (used by services/urs_generation_job.py to constrain Gemini's structured
  output) has no equivalent in NVIDIA's OpenAI-compatible API and is not
  enforced — logged once per call, not silently dropped.
- The response is wrapped so `.text`, `.usage_metadata.prompt_token_count`
  / `.candidates_token_count`, and `.candidates[0].finish_reason` all
  behave like the real google.genai response object (finish_reason is
  mapped onto the real `google.genai.types.FinishReason` enum), since
  services/urs_generation_job.py inspects these directly.
- HTTP/network failures are raised as `google.genai.errors.ServerError` /
  `ClientError` (the same exception types google-genai itself raises) so
  the existing `except errors.ServerError` / `except errors.ClientError`
  handlers in routes/chat.py and routes/validation.py keep working
  unchanged for this provider too.

Never logs prompt or response text (GMP/regulated content) — only
lengths, timings, token counts, and status codes.

Verified against official NVIDIA documentation (2026-08-08):
- Base URL, `/chat/completions` path, `Authorization: Bearer nvapi-...`
  auth, and the request/response field names below (messages, temperature,
  max_tokens, choices[].message.content, choices[].finish_reason,
  usage.{prompt_tokens,completion_tokens}) — Confirmed. Cross-checked
  across docs.nvidia.com's Nemotron 3 Ultra get-started guide,
  docs.api.nvidia.com's chat-completions reference, and litellm's NVIDIA
  NIM provider docs.
- SSE streaming (`data: {...}` lines with `choices[0].delta.content`,
  terminated by `data: [DONE]`) — Confirmed, per the same two first-party
  NVIDIA doc pages.
- `response_format={"type": "json_object"}` support — Likely, not fully
  Confirmed: NVIDIA's own Nemotron 3 Ultra get-started page documents it
  as supported, but the general chat-completions API reference schema
  does not list it. Sent best-effort; a model/deployment that rejects it
  fails that one call with a 400 (surfaced as ClientError, non-fatal to
  the caller — see _generate_batch in urs_generation_job.py), not a
  silent wrong answer.
- Hosted catalog model slug: NVIDIA_MODEL is never hardcoded here (by
  design) — the confirmed catalog id for this model at time of writing is
  `nvidia/nemotron-3-ultra-550b-a55b` (see .env.example), but only the
  operator, reading build.nvidia.com at deploy time, can supply the
  current exact value.
"""

from __future__ import annotations

import json
import logging
import time

import requests
from google.genai import errors as genai_errors
from google.genai import types

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
_DEFAULT_TIMEOUT_SECONDS = 120


def safe_model_label(model: str | None) -> str:
    """Redact `model` for logging unless it demonstrably matches NVIDIA's
    documented catalog-slug shape ('vendor/model-name', e.g.
    'nvidia/nemotron-3-ultra-550b-a55b' — see .env.example) and does not
    carry the 'nvapi-' prefix reserved for API keys (the same prefix check
    factory.py already applies to NVIDIA_API_KEY). NVIDIA_MODEL is normally
    a non-secret identifier safe to log, but nothing prevents a
    misconfigured deployment from putting a real key there instead (see
    Stage 4B: exactly this happened and the key-shaped value was logged in
    plaintext by this file's own request/response log lines) — when the
    shape doesn't match, redact rather than risk logging a secret."""
    if not model:
        return "<unset>"
    if "/" in model and not model.startswith("nvapi-"):
        return model
    return "<redacted: NVIDIA_MODEL does not match the expected 'vendor/model-name' catalog-slug format>"


def _content_text(content) -> str:
    return "".join(getattr(part, "text", "") or "" for part in (content.parts or []))


def _contents_to_messages(contents, system_instruction: str | None) -> list[dict]:
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    for content in contents:
        role = "assistant" if content.role == "model" else "user"
        messages.append({"role": role, "content": _content_text(content)})
    return messages


def _map_finish_reason(reason: str | None):
    if not reason:
        return types.FinishReason.FINISH_REASON_UNSPECIFIED
    return {
        "stop": types.FinishReason.STOP,
        "length": types.FinishReason.MAX_TOKENS,
        "content_filter": types.FinishReason.SAFETY,
    }.get(reason.lower(), types.FinishReason.OTHER)


def _error_body(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {"error": {"message": resp.text}}


def _raise_for_status(resp: requests.Response) -> None:
    if resp.status_code >= 500:
        logger.error("Nemotron request failed: server error %s", resp.status_code)
        raise genai_errors.ServerError(resp.status_code, _error_body(resp), response=resp)
    if resp.status_code >= 400:
        logger.error("Nemotron request failed: client error %s", resp.status_code)
        raise genai_errors.ClientError(resp.status_code, _error_body(resp), response=resp)


class _UsageMetadata:
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_token_count = prompt_tokens
        self.candidates_token_count = completion_tokens


class _Candidate:
    def __init__(self, finish_reason):
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, text: str, finish_reason, prompt_tokens, completion_tokens):
        self.text = text
        self.usage_metadata = _UsageMetadata(prompt_tokens, completion_tokens)
        self.candidates = [_Candidate(finish_reason)]


class _StreamChunk:
    def __init__(self, text: str):
        self.text = text


class _NemotronModels:
    """Implements the subset of google.genai.Client().models used in this
    codebase: generate_content() and generate_content_stream()."""

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int):
        self._model = model
        self._url = base_url
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _build_payload(self, contents, config, stream: bool) -> dict:
        system_instruction = getattr(config, "system_instruction", None) if config else None
        temperature = getattr(config, "temperature", None) if config else None
        max_tokens = getattr(config, "max_output_tokens", None) if config else None
        response_mime_type = getattr(config, "response_mime_type", None) if config else None
        response_schema = getattr(config, "response_schema", None) if config else None

        payload = {
            "model": self._model,
            "messages": _contents_to_messages(contents, system_instruction),
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_mime_type == "application/json":
            payload["response_format"] = {"type": "json_object"}
            if response_schema:
                logger.info(
                    "Nemotron provider: response_schema is not supported by the "
                    "NVIDIA API and is not enforced — falling back to best-effort "
                    "JSON mode (response_format=json_object) only."
                )
        return payload

    # google.genai.Client().models.generate_content(model=..., contents=..., config=...)
    def generate_content(self, *, model=None, contents, config=None):
        payload = self._build_payload(contents, config, stream=False)
        logger.info(
            "Nemotron request: model=%s messages=%d stream=False",
            safe_model_label(self._model), len(payload["messages"]),
        )
        start = time.perf_counter()
        try:
            resp = requests.post(self._url, headers=self._headers, json=payload, timeout=self._timeout)
        except requests.exceptions.RequestException as exc:
            logger.error("Nemotron request failed: network error (%s)", exc.__class__.__name__)
            raise genai_errors.ServerError(503, {"error": {"message": str(exc)}}) from exc
        elapsed = time.perf_counter() - start
        _raise_for_status(resp)

        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content") or "")
        finish_reason = _map_finish_reason(choice.get("finish_reason"))
        usage = data.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")

        logger.info(
            "Nemotron response: model=%s elapsed=%.2fs finish_reason=%s "
            "prompt_tokens=%s completion_tokens=%s",
            safe_model_label(self._model), elapsed, getattr(finish_reason, "name", finish_reason),
            prompt_tokens, completion_tokens,
        )
        return _Response(text, finish_reason, prompt_tokens, completion_tokens)

    # google.genai.Client().models.generate_content_stream(model=..., contents=..., config=...)
    def generate_content_stream(self, *, model=None, contents, config=None):
        payload = self._build_payload(contents, config, stream=True)
        logger.info(
            "Nemotron request: model=%s messages=%d stream=True",
            safe_model_label(self._model), len(payload["messages"]),
        )
        start = time.perf_counter()
        try:
            resp = requests.post(
                self._url, headers=self._headers, json=payload,
                timeout=self._timeout, stream=True,
            )
        except requests.exceptions.RequestException as exc:
            logger.error("Nemotron streaming request failed: network error (%s)", exc.__class__.__name__)
            raise genai_errors.ServerError(503, {"error": {"message": str(exc)}}) from exc
        _raise_for_status(resp)

        chunk_count = 0
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    logger.warning("Nemotron stream: skipped malformed SSE chunk")
                    continue
                delta = ((event.get("choices") or [{}])[0].get("delta") or {})
                text = delta.get("content")
                if text:
                    chunk_count += 1
                    yield _StreamChunk(text)
        finally:
            elapsed = time.perf_counter() - start
            logger.info(
                "Nemotron stream complete: model=%s elapsed=%.2fs chunks=%d",
                safe_model_label(self._model), elapsed, chunk_count,
            )


class NemotronClient:
    """Drop-in replacement for google.genai.Client — see module docstring."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = _DEFAULT_TIMEOUT_SECONDS,
    ):
        self.models = _NemotronModels(api_key=api_key, model=model, base_url=base_url, timeout=timeout)
