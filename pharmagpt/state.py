"""
state.py — Shared runtime state for PharmaGPT.

Holds the active AI provider client and the per-project conversation
history cache. Both are module-level singletons — created once at import
time and shared across all route handlers via a simple import.

Why a separate module?
  app.py previously held these as globals. Now that route handlers live in
  the routes/ package, they need a neutral place to import from that does
  not create circular dependencies with the Flask app object.
"""

from pharmagpt import database as db
from google.genai import types
from pharmagpt.config import AI_PROVIDER, GEMINI_API_KEY, NVIDIA_API_KEY, NVIDIA_MODEL
from pharmagpt.providers.factory import get_ai_client


# ── AI provider client ────────────────────────────────────────────────────────
# One instance shared across all requests. Thread-safe for read-only API calls.
# Kept as `gemini_client` for backward compatibility — every route/service
# module does `from pharmagpt.state import gemini_client`. It now holds
# whichever provider AI_PROVIDER selects (pharmagpt/providers/factory.py);
# both providers expose the same `.models.generate_content()` /
# `.models.generate_content_stream()` surface, so no other file changes.
gemini_client = get_ai_client(
    provider=AI_PROVIDER,
    gemini_api_key=GEMINI_API_KEY,
    nvidia_api_key=NVIDIA_API_KEY,
    nvidia_model=NVIDIA_MODEL,
)


# ── In-memory conversation history cache ─────────────────────────────────────
# Maps project_id (int) → list of types.Content objects.
# Rebuilt from the database on first access per server lifetime.
# Cleared on project delete, conversation clear, or a Gemini API error.
history_cache: dict[int, list] = {}


def get_history(project_id: int) -> list:
    """
    Return the Gemini Content list for a project.

    Loads from the database on first access, then keeps the list in RAM
    so subsequent chat turns do not require a DB round-trip.
    """
    if project_id not in history_cache:
        rows = db.get_project_messages(project_id)
        history_cache[project_id] = [
            types.Content(role=r["role"], parts=[types.Part(text=r["content"])])
            for r in rows
        ]
    return history_cache[project_id]
