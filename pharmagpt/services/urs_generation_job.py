"""
services/urs_generation_job.py — Background execution of URS AI requirement
generation.

Why this exists
----------------
routes/urs.py's /generate endpoint used to call Gemini's
generate_content_stream() and iterate the response *inside* the HTTP
request, holding a gunicorn worker for the entire generation time (all
selected sections in one prompt, up to 8192 output tokens). On Render this
routinely exceeded `--timeout=60` (Procfile/render.yaml), producing:

    [CRITICAL] WORKER TIMEOUT
    POST /urs/1/generate

Streaming the tokens back to the browser did not shorten that time — Gemini
still had to finish generating before the loop could end — it only gave the
UI a character counter.

Fix: generation now runs on services/job_runner.py's thread pool via
submit_generation_job(), split into small batches (config.URS_GENERATION_
BATCH_SIZE sections per Gemini call, generate_content() not _stream()) so no
single call is both large and blocking on the request thread. Progress is
persisted to SQLite (urs_database.start_generation / update_generation_
progress / finish_generation) exactly like the existing document-extraction
jobs in services/document_processor.py — the frontend polls
GET /urs/<id>/generate/status instead of reading an SSE stream.

Resilience layers per batch, in order
--------------------------------------
1. response_schema / response_mime_type="application/json" on the Gemini
   call itself — the model is constrained to emit valid JSON matching the
   requirement shape, which eliminates most markdown-fence/prose wrapping.
2. finish_reason is checked explicitly before trusting the output:
   MAX_TOKENS (truncated) is retried; SAFETY/RECITATION/etc. (blocked) is
   reported immediately as a distinct, non-retryable failure.
3. Automatic retry, but ONLY for malformed/truncated output — a genuine API
   error (network, auth, quota) is never retried and fails the batch on the
   first attempt.
4. If every retry is still malformed, _extract_partial_requirements() scans
   the last raw response for complete {...} requirement objects and salvages
   whatever is usable rather than discarding the whole batch.
5. The job's final generation_message is a human-readable per-section
   summary ("2 of 3 sections generated successfully...") rather than a raw
   error string, built from which sections actually appear in the returned
   requirements — not just which batches nominally succeeded.
"""

from __future__ import annotations

import json
import logging
import time

from pharmagpt import urs_database as udb
from pharmagpt.config import (
    GEMINI_MODEL,
    URS_GENERATION_BATCH_SIZE,
    URS_GENERATION_MAX_RETRIES,
    URS_GENERATION_SLOW_WARNING_SECONDS,
)
from pharmagpt.prompts import PHARMA_SYSTEM_PROMPT
from pharmagpt.services import urs_service as svc
from pharmagpt.services.job_runner import job_runner
from pharmagpt.services.urs_requirement_library import SECTION_PREFIX
from pharmagpt.state import gemini_client
from google.genai import types

logger = logging.getLogger(__name__)


# ── Structured output schema ──────────────────────────────────────────────────
# Forces Gemini to emit a JSON array matching this shape instead of prompting
# it to "return only a JSON array" and hoping — removes markdown fences and
# most prose-wrapping failure modes at the source.
_REQUIREMENT_ARRAY_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "section":              {"type": "STRING"},
            "requirement":          {"type": "STRING"},
            "rationale":            {"type": "STRING"},
            "priority":             {"type": "STRING", "enum": ["Critical", "High", "Medium", "Low"]},
            "gmp_criticality":      {"type": "STRING", "enum": ["GMP-Critical", "GMP", "Non-GMP"]},
            "regulatory_ref":       {"type": "STRING"},
            "verification_method":  {"type": "STRING"},
            "acceptance_criteria":  {"type": "STRING"},
        },
        "required": ["section", "requirement", "priority", "gmp_criticality"],
    },
}


class _RetryableGenerationError(Exception):
    """Malformed or truncated Gemini output — safe to retry, and safe to fall
    back to partial extraction if retries are exhausted. Never raised for
    network/auth/quota failures, which propagate as their original exception
    type and are never retried."""

    def __init__(self, message: str, raw_text: str = ""):
        super().__init__(message)
        self.raw_text = raw_text


class GenerationBlockedError(Exception):
    """Gemini stopped generation for a reason retrying can't fix (safety
    filter, recitation, blocked prompt, ...). Reported immediately rather
    than burning retries against the same filter."""


def submit_generation_job(
    urs_id: int, urs_info: dict, sections: list[str], performed_by: str = "System",
) -> None:
    """
    Kick off background AI generation for a URS and return immediately.

    Batches `sections` into groups of URS_GENERATION_BATCH_SIZE and marks the
    job 'running' (with the correct total) synchronously, before handing off
    to job_runner — so a poll that lands in the gap between this call
    returning and the background thread actually starting still sees
    'running', never a stale 'idle'.

    `performed_by` identifies who triggered generation for the audit trail
    (Generation Started/Completed/Failed entries). It must be resolved by
    the caller (routes/urs.py, from the authenticated request's g.tenant)
    before this call — the background thread runs outside any Flask request
    context, so it has no way to read `g` itself.
    """
    batches = _batch_sections(sections, URS_GENERATION_BATCH_SIZE) or [[]]
    udb.start_generation(urs_id, len(batches))
    udb.add_approval_entry(
        urs_id, "Generation Started", performed_by, "",
        f"{len(sections)} section(s) requested", urs_info.get("revision", "A"),
    )
    job_runner.submit(_run_generation_job, urs_id, urs_info, batches, performed_by)


def _batch_sections(sections: list[str], batch_size: int) -> list[list[str]]:
    return [sections[i:i + batch_size] for i in range(0, len(sections), batch_size)]


def _run_generation_job(
    urs_id: int, urs_info: dict, batches: list[list[str]], performed_by: str = "System",
) -> None:
    """The background job body. Runs on job_runner's thread pool.

    Each batch is generated and parsed independently: a failure in one batch
    (bad JSON, Gemini error) is logged and skipped rather than losing every
    other section's already-generated requirements. Section coverage is
    computed from what actually comes back, not just which batch "succeeded",
    so a partially-recovered batch still gets credited for the sections it
    did produce.

    Each batch's requirements are persisted immediately via
    append_requirements() as soon as that batch completes, rather than
    accumulated in memory and written once in a single bulk save after the
    loop. Two reasons: (1) a process crash mid-job no longer loses every
    already-generated requirement, only the batch in flight; (2) it is what
    makes the final status/count write in finish_generation() genuinely
    atomic — there is no longer a slow bulk-insert step sitting between "the
    last batch's count is known" and "the terminal status is written". A
    batch whose persistence itself fails is treated as failed (not counted),
    since claiming a requirement was "generated" when it was never durably
    saved would be worse than under-reporting it.

    The per-batch progress write (update_generation_progress) is skipped for
    the *last* batch — its contribution to progress/count is folded into the
    single finish_generation() call after the loop instead, so status and
    the final result_count are always published together, never separately.
    """
    job_start = time.perf_counter()
    all_numbered: list[dict] = []
    section_counters: dict[str, int] = {}
    batch_errors: list[str] = []
    requested_sections: list[str] = []
    for batch in batches:
        for s in batch:
            if s and s not in requested_sections:
                requested_sections.append(s)
    covered_sections: set[str] = set()

    for i, batch_sections in enumerate(batches, start=1):
        try:
            batch_reqs, recovery_note = _generate_batch_resilient(
                urs_id, i, len(batches), urs_info, batch_sections,
            )
            if recovery_note:
                batch_errors.append(f"Batch {i} ({', '.join(batch_sections) or 'default sections'}): {recovery_note}")

            numbered_batch: list[dict] = []
            for req in batch_reqs:
                section = req.get("section", "General Requirements")
                prefix = SECTION_PREFIX.get(section, "REQ")
                section_counters[prefix] = section_counters.get(prefix, 0) + 1
                req["req_id"] = f"{prefix}-{section_counters[prefix]:03d}"
                req["source"] = "ai"
                req["status"] = "draft"
                numbered_batch.append(req)

            if numbered_batch:
                udb.append_requirements(urs_id, numbered_batch)
            for req in numbered_batch:
                covered_sections.add(req.get("section", "General Requirements"))
            all_numbered.extend(numbered_batch)
        except GenerationBlockedError as exc:
            logger.error("URS %s generation batch %d/%d blocked: %s", urs_id, i, len(batches), exc)
            batch_errors.append(f"Batch {i} ({', '.join(batch_sections) or 'default sections'}): {exc}")
        except Exception as exc:
            logger.exception("URS %s generation batch %d/%d failed", urs_id, i, len(batches))
            batch_errors.append(f"Batch {i} ({', '.join(batch_sections) or 'default sections'}): {exc}")

        if i < len(batches):
            udb.update_generation_progress(urs_id, i, len(all_numbered))

    status = "failed" if not all_numbered else "completed"
    message = _build_generation_message(requested_sections, covered_sections, len(all_numbered))
    error_summary = "; ".join(batch_errors)
    udb.finish_generation(urs_id, status, len(batches), len(all_numbered), error_summary, message)
    udb.add_approval_entry(
        urs_id, "Generation Completed" if status == "completed" else "Generation Failed",
        performed_by, "", message or error_summary, urs_info.get("revision", "A"),
    )

    total_seconds = time.perf_counter() - job_start
    logger.info(
        "URS %s generation job finished: status=%s requirements=%d sections=%d/%d total=%.2fs errors=%d",
        urs_id, status, len(all_numbered), len(covered_sections), len(requested_sections),
        total_seconds, len(batch_errors),
    )


def _build_generation_message(requested: list[str], covered: set[str], result_count: int) -> str:
    """Human-readable summary for the frontend, e.g.:
    '2 of 3 sections generated successfully (11 requirements). 1 section
    failed and can be retried: Safety Requirements.'"""
    total = len(requested) or 1
    covered_count = len(covered & set(requested)) if requested else (1 if result_count else 0)
    message = f"{covered_count} of {total} section{'s' if total != 1 else ''} generated successfully ({result_count} requirements)."
    missing = [s for s in requested if s not in covered]
    if missing:
        noun = "section" if len(missing) == 1 else "sections"
        message += f" {len(missing)} {noun} failed and can be retried: {', '.join(missing)}."
    return message


def _generate_batch_resilient(
    urs_id: int, batch_num: int, batch_total: int, urs_info: dict, sections: list[str],
) -> tuple[list[dict], str | None]:
    """Generate one batch with automatic retry on malformed/truncated output.

    Only _RetryableGenerationError is retried (bad JSON, MAX_TOKENS
    truncation) — a genuine API error (network, auth, quota) or a
    GenerationBlockedError (safety/recitation) propagates on the first
    attempt without wasting retries. If every attempt still comes back
    malformed, falls back to salvaging whatever complete requirement objects
    can be recovered from the last response instead of discarding the batch.

    Returns (requirements, recovery_note); recovery_note is None on a clean
    parse, otherwise a short description of what was recovered/lost.
    """
    max_attempts = URS_GENERATION_MAX_RETRIES + 1
    last_error: _RetryableGenerationError | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            _raw_text, requirements = _generate_batch(
                urs_id, batch_num, batch_total, urs_info, sections, attempt, max_attempts,
            )
            return requirements, None
        except _RetryableGenerationError as exc:
            last_error = exc
            if attempt < max_attempts:
                logger.warning(
                    "URS %s batch %d/%d attempt %d/%d failed to parse (%s) — retrying",
                    urs_id, batch_num, batch_total, attempt, max_attempts, exc,
                )
                continue
            break

    recovered = _extract_partial_requirements(last_error.raw_text if last_error else "")
    if recovered:
        note = (
            f"recovered {len(recovered)} requirement(s) from malformed/truncated output "
            f"after {max_attempts} attempt(s) ({last_error})"
        )
        logger.warning("URS %s batch %d/%d: %s", urs_id, batch_num, batch_total, note)
        return recovered, note

    raise last_error


def _generate_batch(
    urs_id: int, batch_num: int, batch_total: int, urs_info: dict, sections: list[str],
    attempt: int = 1, max_attempts: int = 1,
) -> tuple[str, list[dict]]:
    """Run one Gemini call for a subset of sections and return (raw_text, parsed_requirements).

    Raises _RetryableGenerationError for malformed JSON or MAX_TOKENS
    truncation (both retryable), GenerationBlockedError for a
    safety/recitation stop (not retryable), or lets any other exception
    (network, auth, quota) propagate untouched (not retryable). Logs
    prompt/response token counts and timing for every attempt regardless of
    outcome.
    """
    prompt = svc.build_generation_prompt(urs_info, sections)

    gemini_start = time.perf_counter()
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        config=types.GenerateContentConfig(
            system_instruction=PHARMA_SYSTEM_PROMPT,
            temperature=0.3,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=_REQUIREMENT_ARRAY_SCHEMA,
        ),
    )
    gemini_seconds = time.perf_counter() - gemini_start

    usage = getattr(response, "usage_metadata", None)
    prompt_tokens = getattr(usage, "prompt_token_count", None)
    response_tokens = getattr(usage, "candidates_token_count", None)

    logger.info(
        "URS %s generation batch %d/%d attempt %d/%d [%s]: gemini=%.2fs prompt_tokens=%s response_tokens=%s",
        urs_id, batch_num, batch_total, attempt, max_attempts,
        ", ".join(sections) or "default sections", gemini_seconds, prompt_tokens, response_tokens,
    )
    if gemini_seconds > URS_GENERATION_SLOW_WARNING_SECONDS:
        logger.warning(
            "URS %s generation batch %d/%d attempt %d took %.2fs (> %ds threshold) — "
            "consider lowering URS_GENERATION_BATCH_SIZE",
            urs_id, batch_num, batch_total, attempt, gemini_seconds, URS_GENERATION_SLOW_WARNING_SECONDS,
        )

    raw_text = response.text or ""
    _check_finish_reason(response, raw_text)

    parse_start = time.perf_counter()
    try:
        requirements = _parse_ai_requirements(raw_text)
    except json.JSONDecodeError as exc:
        parse_seconds = time.perf_counter() - parse_start
        logger.warning(
            "URS %s generation batch %d/%d attempt %d: JSON parse failed in %.3fs (%s)",
            urs_id, batch_num, batch_total, attempt, parse_seconds, exc,
        )
        raise _RetryableGenerationError(f"malformed JSON: {exc}", raw_text=raw_text) from exc
    parse_seconds = time.perf_counter() - parse_start
    logger.info(
        "URS %s generation batch %d/%d attempt %d: parsed %d requirements in %.3fs",
        urs_id, batch_num, batch_total, attempt, len(requirements), parse_seconds,
    )
    return raw_text, requirements


def _check_finish_reason(response, raw_text: str) -> None:
    """Validate why Gemini stopped generating before trusting the output.

    MAX_TOKENS means the JSON is almost certainly truncated — retryable.
    Any other non-STOP reason (SAFETY, RECITATION, PROHIBITED_CONTENT, ...)
    means retrying the identical prompt is unlikely to help, so it's reported
    immediately as a distinct, non-retryable failure instead of being
    silently handed to the JSON parser (where it would just look like
    "malformed JSON" with no indication of the real cause).
    """
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise GenerationBlockedError("Gemini returned no candidates (prompt likely blocked)")

    reason = candidates[0].finish_reason
    if reason in (None, types.FinishReason.STOP, types.FinishReason.FINISH_REASON_UNSPECIFIED):
        return
    if reason == types.FinishReason.MAX_TOKENS:
        raise _RetryableGenerationError("Gemini output was truncated (finish_reason=MAX_TOKENS)", raw_text=raw_text)

    reason_name = getattr(reason, "name", str(reason))
    raise GenerationBlockedError(f"Gemini stopped generation early (finish_reason={reason_name})")


def _parse_ai_requirements(raw_text: str) -> list[dict]:
    """Extract the JSON array of requirements from Gemini's raw text output.

    response_schema/response_mime_type="application/json" mean Gemini should
    not wrap the array in markdown fences any more, but the stripping is kept
    as a cheap defense-in-depth in case a future model/config regresses that."""
    json_str = raw_text.strip()
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0].strip()
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0].strip()
    start = json_str.find("[")
    end = json_str.rfind("]") + 1
    if start >= 0 and end > start:
        json_str = json_str[start:end]
    return json.loads(json_str)


def _extract_partial_requirements(raw_text: str) -> list[dict]:
    """Best-effort recovery of complete requirement objects from malformed or
    truncated JSON — used only after every retry has failed.

    Scans for balanced {...} substrings (bracket-depth counting) and keeps
    whichever ones parse cleanly on their own and contain the minimum
    required fields, discarding a truncated trailing object rather than
    losing the whole batch. This is a heuristic, not a JSON parser: a string
    value containing a literal '{' or '}' could throw off the depth count,
    but requirement text in practice never does.
    """
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1]
    elif "```" in text:
        text = text.split("```", 1)[1]

    recovered: list[dict] = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = text[start:i + 1]
                    start = None
                    try:
                        obj = json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict) and obj.get("section") and obj.get("requirement"):
                        recovered.append(obj)
    return recovered
