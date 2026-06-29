"""
documents.py — File storage utilities for PharmaGPT.

Responsibilities
----------------
1. Validate file types against the allowed list.
2. Save uploaded files to disk, resolving filename collisions safely.
3. Resolve and delete files from disk.
4. Provide MIME types for serving files in the browser.

Storage layout
--------------
Project documents : uploads/{project_id}/{stored_filename}
Knowledge Base    : uploads/kb/{stored_filename}

This module never touches the database — all DB work lives in database.py.
Text extraction from file content lives in services/extractor.py.
"""

import os
from werkzeug.utils import secure_filename
from pharmagpt.config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS


# ── File type helpers ─────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    """Return True only if the file extension is in ALLOWED_EXTENSIONS."""
    return "." in filename and get_extension(filename) in ALLOWED_EXTENSIONS


def get_extension(filename: str) -> str:
    """Return the lowercased file extension without the leading dot."""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


# MIME types used when serving files so the browser handles them correctly.
MIME_TYPES = {
    "pdf":  "application/pdf",
    "txt":  "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# File types that browsers can display inline — others trigger a forced download.
VIEWABLE_IN_BROWSER = {"pdf", "txt"}


def get_mime_type(extension: str) -> str:
    """Return the MIME type for a given extension, defaulting to octet-stream."""
    return MIME_TYPES.get(extension, "application/octet-stream")


# ── Shared filename collision helper ─────────────────────────────────────────

def _resolve_collision(upload_dir: str, safe_name: str) -> str:
    """
    Return a filename that does not collide with any existing file in upload_dir.

    If safe_name is free, it is returned unchanged.
    Otherwise appends _1, _2, … to the base until a free slot is found:
        report.pdf  →  report_1.pdf  →  report_2.pdf  …
    """
    if not os.path.exists(os.path.join(upload_dir, safe_name)):
        return safe_name

    base, ext = os.path.splitext(safe_name)
    counter   = 1
    while os.path.exists(os.path.join(upload_dir, f"{base}_{counter}{ext}")):
        counter += 1
    return f"{base}_{counter}{ext}"


# ── Project document storage ──────────────────────────────────────────────────

def get_project_upload_dir(project_id: int) -> str:
    """Return the upload directory for a project, creating it if needed."""
    path = os.path.join(UPLOAD_FOLDER, str(project_id))
    os.makedirs(path, exist_ok=True)
    return path


def safe_save(file, project_id: int) -> tuple[str, int]:
    """
    Save a Werkzeug FileStorage object to the project's upload directory.

    Sanitises the filename with secure_filename() to prevent path traversal,
    then resolves any name collisions with _resolve_collision().

    Returns
    -------
    stored_filename : str — the sanitised name actually written to disk
    file_size       : int — bytes written
    """
    safe_name  = secure_filename(file.filename)
    upload_dir = get_project_upload_dir(project_id)
    safe_name  = _resolve_collision(upload_dir, safe_name)

    file_path = os.path.join(upload_dir, safe_name)
    file.save(file_path)
    return safe_name, os.path.getsize(file_path)


def get_file_path(project_id: int, stored_filename: str) -> str:
    """Return the absolute path to a stored project file."""
    return os.path.join(get_project_upload_dir(project_id), stored_filename)


def delete_from_disk(project_id: int, stored_filename: str) -> None:
    """Remove a project file from disk. Silently does nothing if already missing."""
    path = get_file_path(project_id, stored_filename)
    if os.path.exists(path):
        os.remove(path)


def file_exists(project_id: int, stored_filename: str) -> bool:
    """Return True if the project file is present on disk."""
    return os.path.exists(get_file_path(project_id, stored_filename))


# ── Knowledge Base file storage ───────────────────────────────────────────────
# KB files are stored globally (not per-project) at uploads/kb/

def get_kb_upload_dir() -> str:
    """Return the KB upload directory, creating it if needed."""
    path = os.path.join(UPLOAD_FOLDER, "kb")
    os.makedirs(path, exist_ok=True)
    return path


def safe_save_kb(file) -> tuple[str, int]:
    """
    Save a KB file upload to uploads/kb/, resolving name collisions.
    Returns (stored_filename, file_size_in_bytes).
    """
    safe_name  = secure_filename(file.filename)
    upload_dir = get_kb_upload_dir()
    safe_name  = _resolve_collision(upload_dir, safe_name)

    file_path = os.path.join(upload_dir, safe_name)
    file.save(file_path)
    return safe_name, os.path.getsize(file_path)


def get_kb_file_path(stored_filename: str) -> str:
    """Return the absolute path for a KB stored file."""
    return os.path.join(get_kb_upload_dir(), stored_filename)


def delete_kb_from_disk(stored_filename: str) -> None:
    """Remove a KB file from disk. Silently does nothing if already missing."""
    path = get_kb_file_path(stored_filename)
    if os.path.exists(path):
        os.remove(path)


def kb_file_exists(stored_filename: str) -> bool:
    """Return True if the KB file is present on disk."""
    return os.path.exists(get_kb_file_path(stored_filename))
