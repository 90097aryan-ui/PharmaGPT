"""
documents.py — File storage utilities for the PharmaGPT Documents module.

Responsibilities
────────────────
1. Validate file types against the allowed list.
2. Save uploaded files to disk under  uploads/{project_id}/{filename}.
3. Resolve and delete files from disk.
4. Provide MIME types for serving files in the browser.
5. Expose stub functions for AI document analysis (implemented in v0.5).

This module never touches the database — all DB work lives in database.py.
"""

import os
from werkzeug.utils import secure_filename
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS


# ── File type helpers ─────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    """Return True only if the file extension is in ALLOWED_EXTENSIONS."""
    return "." in filename and get_extension(filename) in ALLOWED_EXTENSIONS


def get_extension(filename: str) -> str:
    """Return the lowercased file extension without the leading dot."""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


# MIME types used when serving files so the browser handles them correctly.
# PDF and TXT can be rendered inline; DOCX and XLSX trigger a download.
MIME_TYPES = {
    "pdf":  "application/pdf",
    "txt":  "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# File types that browsers can display inline (no forced download needed for "View")
VIEWABLE_IN_BROWSER = {"pdf", "txt"}


def get_mime_type(extension: str) -> str:
    """Return the MIME type for a given extension, defaulting to octet-stream."""
    return MIME_TYPES.get(extension, "application/octet-stream")


# ── Disk storage ──────────────────────────────────────────────────────────────

def get_project_upload_dir(project_id: int) -> str:
    """
    Return the upload directory path for a project, creating it if it
    does not already exist.  Path: uploads/{project_id}/
    """
    path = os.path.join(UPLOAD_FOLDER, str(project_id))
    os.makedirs(path, exist_ok=True)
    return path


def safe_save(file, project_id: int) -> tuple[str, int]:
    """
    Save a Werkzeug FileStorage object to the project's upload folder.

    Sanitises the filename with secure_filename() to prevent path traversal.
    If a file with the same name already exists, appends _1, _2, … until
    a free slot is found.

    Returns
    -------
    stored_filename : str   — the sanitised name actually written to disk
    file_size       : int   — bytes written (measured after save)
    """
    safe_name = secure_filename(file.filename)
    upload_dir = get_project_upload_dir(project_id)
    file_path = os.path.join(upload_dir, safe_name)

    # Resolve name collisions
    if os.path.exists(file_path):
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(file_path):
            safe_name = f"{base}_{counter}{ext}"
            file_path = os.path.join(upload_dir, safe_name)
            counter += 1

    file.save(file_path)
    file_size = os.path.getsize(file_path)
    return safe_name, file_size


def get_file_path(project_id: int, stored_filename: str) -> str:
    """Return the absolute path to a stored file."""
    return os.path.join(get_project_upload_dir(project_id), stored_filename)


def delete_from_disk(project_id: int, stored_filename: str) -> None:
    """Remove a file from disk. Silently does nothing if the file is missing."""
    path = get_file_path(project_id, stored_filename)
    if os.path.exists(path):
        os.remove(path)


def file_exists(project_id: int, stored_filename: str) -> bool:
    """Return True if the file is present on disk."""
    return os.path.exists(get_file_path(project_id, stored_filename))


# ── Knowledge Base file storage ───────────────────────────────────────────────
# KB files are stored globally (not per-project) at uploads/kb/

def get_kb_upload_dir() -> str:
    """Return the KB upload directory, creating it if needed."""
    path = os.path.join(UPLOAD_FOLDER, "kb")
    os.makedirs(path, exist_ok=True)
    return path


def safe_save_kb(file) -> tuple[str, int]:
    """Save a KB file upload to uploads/kb/, avoiding name collisions."""
    safe_name = secure_filename(file.filename)
    upload_dir = get_kb_upload_dir()
    file_path = os.path.join(upload_dir, safe_name)

    if os.path.exists(file_path):
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(file_path):
            safe_name = f"{base}_{counter}{ext}"
            file_path = os.path.join(upload_dir, safe_name)
            counter += 1

    file.save(file_path)
    return safe_name, os.path.getsize(file_path)


def get_kb_file_path(stored_filename: str) -> str:
    """Return the absolute path for a KB stored file."""
    return os.path.join(get_kb_upload_dir(), stored_filename)


def delete_kb_from_disk(stored_filename: str) -> None:
    """Remove a KB file from disk. Silently does nothing if missing."""
    path = get_kb_file_path(stored_filename)
    if os.path.exists(path):
        os.remove(path)


def kb_file_exists(stored_filename: str) -> bool:
    """Return True if the KB file is present on disk."""
    return os.path.exists(get_kb_file_path(stored_filename))


# ── AI document analysis stubs (v0.5) ────────────────────────────────────────
# These functions are intentionally unimplemented.  In v0.5 they will extract
# text from documents and pass it to Gemini for GMP-aware analysis.

def extract_text(file_path: str, extension: str) -> str:
    """
    Extract plain text from a document file.
    Supports: pdf (via pdfplumber), docx (via python-docx),
              xlsx (via openpyxl), txt (direct read).
    Raises NotImplementedError until v0.5 implements extraction.
    """
    raise NotImplementedError(
        "Document text extraction will be implemented in v0.5. "
        f"Requested: {extension} at {file_path}"
    )


def analyze_with_gemini(text: str, user_prompt: str, gemini_client) -> str:
    """
    Send extracted document text + a user question to Gemini and return
    the AI response.  Called by the /documents/<id>/analyze route (v0.5).
    """
    raise NotImplementedError(
        "AI document analysis will be implemented in v0.5."
    )
