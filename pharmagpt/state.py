"""
state.py — Shared runtime state for PharmaGPT.

Holds the Gemini API client and the per-project conversation history cache.
Both are module-level singletons — created once at import time and shared
across all route handlers via a simple import.

Why a separate module?
  app.py previously held these as globals. Now that route handlers live in
  the routes/ package, they need a neutral place to import from that does
  not create circular dependencies with the Flask app object.
"""

from pharmagpt import database as db
from google import genai
from google.genai import types
from pharmagpt.config import GEMINI_API_KEY


# ── Gemini client ─────────────────────────────────────────────────────────────
# One instance shared across all requests. Thread-safe for read-only API calls.
gemini_client = genai.Client(api_key=GEMINI_API_KEY)


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
