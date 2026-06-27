"""
routes/chat.py — SSE streaming chat endpoint.

Route
-----
POST /stream   stream a Gemini response, optionally injecting document context
"""

import json

import database as db
from flask import Blueprint, jsonify, request, Response, stream_with_context
from google.genai import errors, types
from prompts import PHARMA_SYSTEM_PROMPT
from services.document_search import search_project_documents
from state import gemini_client, get_history, history_cache
from config import GEMINI_MODEL

bp = Blueprint("chat", __name__)


@bp.route("/stream", methods=["POST"])
def stream():
    """
    SSE streaming chat endpoint.

    Body:   { "message": "...", "project_id": 3, "use_documents": false }
    Stream: data: {"chunk": "..."}\n\n
            data: {"done": true, "sources": [...]}\n\n
            data: {"error": "..."}\n\n

    When use_documents=true the user's message is searched against all
    extracted document texts for the project. The top relevant chunks are
    prepended to the Gemini prompt. Source filenames are returned in the
    "done" event so the UI can render the Sources strip beneath the response.

    Important: all request data is resolved *before* entering the generator
    because Flask's request context is unavailable inside a streaming generator.
    """
    data          = request.get_json()
    user_message  = data.get("message", "").strip()
    project_id    = data.get("project_id")
    use_documents = bool(data.get("use_documents", False))

    if not user_message:
        return jsonify({"error": "Empty message"}), 400
    if not project_id:
        return jsonify({"error": "No project selected. Please select or create a project first."}), 400

    project = db.get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # ── Document context (RAG) ───────────────────────────────────────────────
    doc_context = ""
    doc_sources = []

    if use_documents:
        result = search_project_documents(user_message, project_id)
        if result["found"]:
            doc_context = result["context_text"]
            doc_sources = result["sources"]

    # Gemini receives the full context-enriched message; the DB stores only
    # the clean user message so the chat history is human-readable.
    gemini_message = (doc_context + user_message) if doc_context else user_message

    history = get_history(project_id)
    history.append(types.Content(role="user", parts=[types.Part(text=gemini_message)]))
    db.save_message(project_id, "user", user_message)

    # Capture sources in the outer scope so the generator closure can read them.
    captured_sources = doc_sources

    def generate():
        reply_parts: list[str] = []
        try:
            for chunk in gemini_client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=PHARMA_SYSTEM_PROMPT,
                ),
            ):
                if chunk.text:
                    reply_parts.append(chunk.text)
                    yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"

            full_reply = "".join(reply_parts)
            history.append(types.Content(role="model", parts=[types.Part(text=full_reply)]))
            db.save_message(project_id, "model", full_reply)
            yield f"data: {json.dumps({'done': True, 'sources': captured_sources})}\n\n"

        except errors.ServerError:
            # Server errors are transient — roll back the optimistic history append
            # and clear the cache so it rebuilds cleanly from the DB on next request.
            history.pop()
            db.clear_project_messages(project_id)
            history_cache.pop(project_id, None)
            yield f"data: {json.dumps({'error': 'Gemini server is temporarily unavailable. Please try again.'})}\n\n"

        except errors.ClientError as exc:
            history.pop()
            history_cache.pop(project_id, None)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
