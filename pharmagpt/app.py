import json
import uuid
from flask import Flask, request, jsonify, render_template, session, Response, stream_with_context, send_file
from google import genai
from google.genai import errors, types
from config import GEMINI_API_KEY, GEMINI_MODEL, FLASK_SECRET_KEY, FLASK_DEBUG, FLASK_PORT, MAX_FILE_SIZE
from prompts import PHARMA_SYSTEM_PROMPT
import database as db
import documents as docs
from services import pdf_reader, docx_reader, excel_reader
from services.document_search import search_project_documents
from services.doc_generator import build_generation_prompt
from services.doc_exporter import markdown_to_docx

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE   # reject uploads over 50 MB

# Gemini client — created once at startup, shared across all requests
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Create SQLite tables if they don't exist yet
db.init_db()

# ── In-memory history cache ───────────────────────────────────────────────────
# Maps project_id (int) → list of types.Content objects.
# Built from the database on first access, then kept in RAM for speed.
# If the server restarts, it is rebuilt from the DB on the next request.
history_cache: dict[int, list] = {}


def get_history(project_id: int) -> list:
    """Return the in-memory Content list for a project, loading from DB if needed."""
    if project_id not in history_cache:
        rows = db.get_project_messages(project_id)
        history_cache[project_id] = [
            types.Content(role=r["role"], parts=[types.Part(text=r["content"])])
            for r in rows
        ]
    return history_cache[project_id]


# ── Page route ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main page. Assign a session ID to new visitors."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return render_template("index.html")


# ── Project routes ────────────────────────────────────────────────────────────

@app.route("/projects", methods=["GET"])
def list_projects():
    """Return all projects as a JSON array, newest first."""
    return jsonify(db.get_all_projects())


@app.route("/projects", methods=["POST"])
def create_project():
    """
    Create a new project.
    Body: { name, equipment_name, manufacturer, department, validation_type }
    Returns the newly created project dict including its auto-assigned id.
    """
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400

    project = db.create_project(
        name=name,
        equipment_name=data.get("equipment_name", "").strip(),
        manufacturer=data.get("manufacturer", "").strip(),
        department=data.get("department", "").strip(),
        validation_type=data.get("validation_type", "").strip(),
    )
    return jsonify(project), 201


@app.route("/projects/<int:project_id>", methods=["GET"])
def get_project(project_id):
    """Return a single project by ID."""
    project = db.get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project)


@app.route("/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    """Delete a project and all its messages."""
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    db.delete_project(project_id)
    # Also remove from in-memory cache
    history_cache.pop(project_id, None)
    return jsonify({"status": "deleted"})


@app.route("/projects/<int:project_id>/messages", methods=["GET"])
def project_messages(project_id):
    """Return saved messages for a project so the UI can replay them."""
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(db.get_project_messages(project_id))


# ── Streaming chat route ──────────────────────────────────────────────────────

@app.route("/stream", methods=["POST"])
def stream():
    """
    SSE streaming endpoint.

    Body:   { "message": "...", "project_id": 3, "use_documents": false }
    Stream: data: {"chunk": "..."}\n\n
            data: {"done": true, "sources": [...]}\n\n
            data: {"error": "..."}\n\n

    When use_documents=true the user's message is searched against all extracted
    document texts for the project. The top relevant chunks are prepended to the
    Gemini prompt. Source document names are returned in the "done" event so the
    UI can render a Sources panel below the AI response.
    """
    data = request.get_json()
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

    # ── Document context (RAG-lite) ──────────────────────────────────────────
    # Resolved outside the generator so sources are captured for the done event.
    doc_context = ""
    doc_sources = []

    if use_documents:
        result = search_project_documents(user_message, project_id)
        if result["found"]:
            doc_context = result["context_text"]
            doc_sources = result["sources"]

    # Build the message actually sent to Gemini (with document context prepended)
    gemini_message = (doc_context + user_message) if doc_context else user_message

    # Load this project's conversation history (from cache or DB)
    history = get_history(project_id)

    # Append user turn BEFORE entering the generator
    # (Flask request context is unavailable inside streaming generators)
    history.append(types.Content(role="user", parts=[types.Part(text=gemini_message)]))
    db.save_message(project_id, "user", user_message)   # store clean message (no context blob)

    sources_for_done = doc_sources

    def generate():
        full_reply = ""
        try:
            for chunk in gemini_client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=PHARMA_SYSTEM_PROMPT,
                ),
            ):
                if chunk.text:
                    full_reply += chunk.text
                    yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"

            # Stream complete — persist the AI reply
            history.append(types.Content(role="model", parts=[types.Part(text=full_reply)]))
            db.save_message(project_id, "model", full_reply)
            yield f"data: {json.dumps({'done': True, 'sources': sources_for_done})}\n\n"

        except errors.ServerError:
            history.pop()
            db.clear_project_messages(project_id)
            history_cache.pop(project_id, None)
            yield f"data: {json.dumps({'error': 'Gemini server is temporarily unavailable. Please try again.'})}\n\n"

        except errors.ClientError as e:
            history.pop()
            history_cache.pop(project_id, None)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Clear route ───────────────────────────────────────────────────────────────

@app.route("/clear", methods=["POST"])
def clear():
    """Clear all messages for the given project (both DB and in-memory cache)."""
    data = request.get_json() or {}
    project_id = data.get("project_id")
    if project_id:
        db.clear_project_messages(project_id)
        history_cache.pop(project_id, None)
    return jsonify({"status": "cleared"})


# ── Document routes ───────────────────────────────────────────────────────────

@app.route("/projects/<int:project_id>/documents", methods=["GET"])
def list_documents(project_id):
    """Return all document metadata rows for a project, newest first."""
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(db.get_project_documents(project_id))


@app.route("/projects/<int:project_id>/documents", methods=["POST"])
def upload_document(project_id):
    """
    Accept a multipart/form-data file upload and store it inside the project.
    After saving, extract text from the file and store it in document_text.

    Form field: file  (the uploaded file)
    Returns the new document metadata dict on success.
    """
    project = db.get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    if not docs.allowed_file(file.filename):
        return jsonify({"error": "File type not allowed. Accepted: PDF, DOCX, XLSX, TXT"}), 400

    # Save to disk and get the sanitised stored filename and byte count
    stored_filename, file_size = docs.safe_save(file, project_id)
    extension = docs.get_extension(file.filename)

    # Persist metadata to the database
    doc = db.save_document(
        project_id=project_id,
        original_name=file.filename,
        stored_filename=stored_filename,
        file_type=extension,
        file_size=file_size,
    )

    # Extract text immediately — failures are absorbed, upload still succeeds
    _extract_and_store(doc["id"], project_id,
                       docs.get_file_path(project_id, stored_filename), extension)

    return jsonify(doc), 201


def _extract_and_store(doc_id: int, project_id: int, file_path: str, extension: str) -> None:
    """
    Extract text from a newly uploaded document and persist it to document_text.
    Called synchronously during upload. Any exception is caught so the upload
    HTTP response is never blocked by extraction errors.
    """
    try:
        if extension == "pdf":
            text, pages = pdf_reader.extract(file_path)
        elif extension == "docx":
            text, pages = docx_reader.extract(file_path)
        elif extension == "xlsx":
            text, pages = excel_reader.extract(file_path)
        elif extension == "txt":
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            pages = max(1, len(text.split()) // 300)
        else:
            return

        word_count = len(text.split())
        status = "ok" if text.strip() else "empty"
        db.save_document_text(doc_id, project_id, text, pages, word_count, status)

    except Exception:
        db.save_document_text(doc_id, project_id, "", 0, 0, "error")


@app.route("/documents/<int:doc_id>/view")
def view_document(doc_id):
    """
    Serve a document so the browser can display it inline (PDF, TXT).
    For DOCX and XLSX — which browsers cannot render — falls back to download.
    """
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    file_path = docs.get_file_path(doc["project_id"], doc["stored_filename"])
    if not docs.file_exists(doc["project_id"], doc["stored_filename"]):
        return jsonify({"error": "File not found on disk"}), 404

    as_attachment = doc["file_type"] not in docs.VIEWABLE_IN_BROWSER
    return send_file(
        file_path,
        mimetype=docs.get_mime_type(doc["file_type"]),
        as_attachment=as_attachment,
        download_name=doc["original_name"],
    )


@app.route("/documents/<int:doc_id>/download")
def download_document(doc_id):
    """Force-download a document regardless of file type."""
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    file_path = docs.get_file_path(doc["project_id"], doc["stored_filename"])
    if not docs.file_exists(doc["project_id"], doc["stored_filename"]):
        return jsonify({"error": "File not found on disk"}), 404

    return send_file(
        file_path,
        mimetype=docs.get_mime_type(doc["file_type"]),
        as_attachment=True,
        download_name=doc["original_name"],
    )


@app.route("/documents/<int:doc_id>", methods=["DELETE"])
def delete_document(doc_id):
    """Delete a document's metadata from the DB and its file from disk.
    ON DELETE CASCADE in the DB removes the document_text row automatically."""
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    docs.delete_from_disk(doc["project_id"], doc["stored_filename"])
    db.delete_document(doc_id)
    return jsonify({"status": "deleted"})


# ── Document Insights route ───────────────────────────────────────────────────

@app.route("/projects/<int:project_id>/insights", methods=["GET"])
def project_insights(project_id):
    """
    Return aggregated document statistics for the Insights panel.

    Response: {
        document_count, total_pages, total_words, extracted_count,
        last_upload, file_types: {pdf: N, docx: N, ...}
    }
    """
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(db.get_project_insights(project_id))


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION DOCUMENT GENERATOR ROUTES  (v0.6)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/validation/generate", methods=["POST"])
def validation_generate():
    """
    SSE endpoint: generate a validation document with Gemini.

    Body: {
        "doc_type":    "OQ" | "IQ" | "PQ" | ...,
        "project_id":  3,
        "form_data":   { equipment Step-1 fields, "details": { Step-2 fields } },
        "doc_ids":     [1, 2]   -- optional; IDs of docs to include as context
    }
    Stream: data: {"chunk": "..."}\n\n
            data: {"done": true}\n\n
            data: {"error": "..."}\n\n
    """
    body       = request.get_json()
    doc_type   = body.get("doc_type", "OQ")
    project_id = body.get("project_id")
    form_data  = body.get("form_data", {})
    doc_ids    = body.get("doc_ids", [])    # selected document IDs from Step 3

    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    project = db.get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # ── Build document context from selected uploaded files ──────────────────
    doc_context = ""
    if doc_ids:
        # Use document_search to pull relevant text from the selected documents
        from services.document_search import search_project_documents
        result = search_project_documents(
            query=f"{doc_type} validation {form_data.get('equipment_name', '')}",
            project_id=project_id,
            top_k=8,
            max_context_words=3000,
        )
        if result["found"]:
            doc_context = result["context_text"]

    # ── Build Gemini prompt ──────────────────────────────────────────────────
    form_data["project_name"] = project["name"]
    prompt = build_generation_prompt(doc_type, form_data, doc_context, project["name"])

    def generate():
        full_content = ""
        try:
            for chunk in gemini_client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=PHARMA_SYSTEM_PROMPT,
                    temperature=0.3,   # lower temperature for consistent document structure
                ),
            ):
                if chunk.text:
                    full_content += chunk.text
                    yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except errors.ServerError:
            yield f"data: {json.dumps({'error': 'Gemini server temporarily unavailable. Please try again.'})}\n\n"

        except errors.ClientError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/validation/export/docx", methods=["POST"])
def validation_export_docx():
    """
    Convert markdown document content to DOCX and return it as a download.

    Body: {
        "doc_type":  "OQ",
        "title":     "HPLC OQ Protocol",
        "form_data": { ... },
        "content":   "# OPERATIONAL QUALIFICATION PROTOCOL\n..."
    }
    """
    body      = request.get_json()
    doc_type  = body.get("doc_type", "DOC")
    title     = body.get("title", f"{doc_type} Protocol")
    form_data = body.get("form_data", {})
    content   = body.get("content", "")

    if not content:
        return jsonify({"error": "No content to export"}), 400

    try:
        docx_bytes = markdown_to_docx(content, doc_type, form_data)
    except Exception as e:
        return jsonify({"error": f"Export failed: {e}"}), 500

    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    filename   = f"{safe_title}.docx"

    from io import BytesIO
    return send_file(
        BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/validation/save", methods=["POST"])
def validation_save():
    """
    Save a generated validation document to the project.

    Body: {
        "project_id": 3,
        "doc_type":   "OQ",
        "title":      "HPLC OQ Protocol",
        "form_data":  { ... },
        "content":    "..."
    }
    """
    body       = request.get_json()
    project_id = body.get("project_id")
    doc_type   = body.get("doc_type", "DOC")
    title      = body.get("title", f"{doc_type} Document")
    form_data  = body.get("form_data", {})
    content    = body.get("content", "")

    if not project_id or not content:
        return jsonify({"error": "project_id and content are required"}), 400

    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404

    doc = db.save_generated_document(
        project_id=project_id,
        doc_type=doc_type,
        title=title,
        form_data_json=json.dumps(form_data),
        content=content,
    )
    return jsonify({"status": "saved", "id": doc["id"]}), 201


@app.route("/projects/<int:project_id>/generated-docs", methods=["GET"])
def list_generated_docs(project_id):
    """Return all saved generated documents for a project (metadata only)."""
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(db.get_project_generated_documents(project_id))


@app.route("/generated-docs/<int:doc_id>", methods=["GET"])
def get_generated_doc(doc_id):
    """Return a single generated document (including full content)."""
    doc = db.get_generated_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    return jsonify(doc)


@app.route("/generated-docs/<int:doc_id>", methods=["DELETE"])
def delete_generated_doc(doc_id):
    """Delete a saved generated document."""
    if not db.get_generated_document(doc_id):
        return jsonify({"error": "Document not found"}), 404
    db.delete_generated_document(doc_id)
    return jsonify({"status": "deleted"})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
