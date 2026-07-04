"""
services/qms_shared.py — Shared AI-call helpers for the Quality Management Suite.

The three QMS module services (qms_document_service, qms_deviation_service,
qms_capa_service) all call Gemini the same way risk_service.py does. Rather
than re-implementing `_call_gemini`/`_parse_json_response` three times (as
each existing suite currently does independently), QMS defines them once
here and every QMS service imports them.
"""

from __future__ import annotations
import json
import re

from pharmagpt.state import gemini_client
from pharmagpt.config import GEMINI_MODEL
from pharmagpt.prompts import PHARMA_SYSTEM_PROMPT
from google.genai import types


def call_gemini(prompt: str, temperature: float = 0.3) -> str:
    """Call Gemini with the standard PharmaGPT system persona. Returns '' on error."""
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=PHARMA_SYSTEM_PROMPT,
                temperature=temperature,
            ),
        )
        return response.text or ""
    except Exception:
        return ""


def stream_gemini(prompt: str, temperature: float = 0.4):
    """Yield text chunks from a streaming Gemini call. Used for SSE endpoints."""
    for chunk in gemini_client.models.generate_content_stream(
        model=GEMINI_MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        config=types.GenerateContentConfig(
            system_instruction=PHARMA_SYSTEM_PROMPT,
            temperature=temperature,
        ),
    ):
        if chunk.text:
            yield chunk.text


def parse_json_response(text: str, default=None):
    """Extract and parse the first JSON array or object from a Gemini response,
    tolerating markdown code fences and leading/trailing prose."""
    if default is None:
        default = []
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for pattern in (r"\[[\s\S]*\]", r"\{[\s\S]*\}"):
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
    return default
