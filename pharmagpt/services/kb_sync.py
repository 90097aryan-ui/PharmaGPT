"""
services/kb_sync.py — Auto-publish approved governed documents into the
Knowledge Base as their current effective version (PharmaGPT Phase 2 /
Product Recovery Package FINAL_DELIVERABLE.md Q8: "Knowledge Base
version-drift... should be automatic, never a manual cross-check").

Called from the approval routes of every module that reaches a real
"current effective version" state: Document Control (Effective), URS
(Effective), Qualification protocols (approved), Validation Report
(released). Each caller already has the record's markdown content built
via that module's own existing export/report builder (the same one its
"Export DOCX" button already uses) — this module does not build content,
generate anything with AI, or know about any specific module; it only
turns already-approved markdown into a stored KB file and an upserted
kb_documents row.

Idempotent: one governed record always maps to exactly one kb_documents
row (found via source_type/source_id), updated in place on every
re-publish, so the KB never accumulates stale duplicate versions of the
same document — it always shows the current effective version, matching
the "no manual upload, always current" requirement. No new document
types are introduced: the KB folder is chosen from the record's own
doc_type using the existing KB_FOLDERS list, defaulting to "Others" for
any doc_type that doesn't map to a more specific folder (this is
intentionally generic — it costs nothing to extend to a doc_type this
codebase doesn't have yet, e.g. a future BMR/BPR/MFR, without any code
change here).
"""

import logging
import os

from werkzeug.utils import secure_filename

from pharmagpt import database as db
from pharmagpt import documents as doc_utils
from pharmagpt.services.doc_exporter import markdown_to_docx
from pharmagpt.services.document_processor import process_document_async

logger = logging.getLogger(__name__)

# Maps a record's own doc_type/protocol_type to the existing KB folder it
# belongs in (db.KB_FOLDERS) — not a new taxonomy, just a routing table onto
# the one that already exists.
_FOLDER_BY_DOC_TYPE = {
    "SOP": "SOP", "Policy": "SOP", "Work Instruction": "SOP", "Manual": "SOP",
    "URS": "Validation",
    "IQ": "Qualification", "OQ": "Qualification", "PQ": "Qualification",
    "DQ": "Qualification",
    "FAT": "Protocols", "SAT": "Protocols", "Protocol": "Protocols",
    "Test Method": "Protocols", "Checklist": "Protocols",
}


def _folder_for(doc_type: str) -> str:
    return _FOLDER_BY_DOC_TYPE.get(doc_type, "Reports" if "report" in (doc_type or "").lower() else "Others")


def publish_to_kb(*, source_type: str, source_id: int, company_id: str,
                  title: str, doc_type: str, doc_number: str, version: str,
                  content_markdown: str, effective_date: str | None,
                  form_data: dict | None = None) -> dict:
    """
    Publish (or re-publish) a governed record's current effective content to
    the Knowledge Base. Safe to call every time a record re-enters its
    effective/approved/released state — subsequent calls update the same
    kb_documents row rather than creating a new one.

    Parameters
    ----------
    source_type       : "document" | "urs" | "qualification_protocol" | "report"
                         — the qms_audit_trail-style record_type this came from.
    source_id          : the record's own id (or protocol id, for Qualification).
    company_id         : authenticated tenant's company_id (never client-supplied).
    title, doc_type,
    doc_number, version : the record's own descriptive fields (KB metadata only —
                         this function does not validate or constrain doc_type).
    content_markdown   : already-approved, human-reviewed markdown (no AI call
                         happens here).
    effective_date      : ISO date string or None.
    form_data           : passed through to markdown_to_docx() for the DOCX
                         letterhead fields (equipment_name, department, etc.);
                         defaults to {"title": title} if omitted.

    Returns the resulting kb_documents row.
    """
    docx_bytes = markdown_to_docx(content_markdown, doc_type, form_data or {"title": title})

    existing = db.get_kb_document_by_source(source_type, source_id, company_id)

    upload_dir = doc_utils.get_kb_upload_dir()
    base_name = secure_filename(f"{doc_number or title}.docx") or f"{source_type}-{source_id}.docx"
    if existing:
        # Reuse the same stored filename where possible so re-publishing a
        # document doesn't leave the previous version's file orphaned on disk.
        old_path = doc_utils.get_kb_file_path(existing["stored_filename"])
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                logger.warning("kb_sync: could not remove superseded file %s", old_path)
    stored_filename = doc_utils._resolve_collision(upload_dir, base_name)
    file_path = os.path.join(upload_dir, stored_filename)
    with open(file_path, "wb") as f:
        f.write(docx_bytes)
    file_size = os.path.getsize(file_path)

    if existing:
        db.update_kb_document_file(
            existing["id"], title=title, doc_version=version, effective_date=effective_date,
            original_name=base_name, stored_filename=stored_filename,
            file_type="docx", file_size=file_size,
        )
        kb_id = existing["id"]
    else:
        kb_doc = db.create_kb_document(
            title=title, folder=_folder_for(doc_type), tags=f"auto-published,{doc_type}".strip(","),
            doc_version=version, effective_date=effective_date, review_date=None,
            original_name=base_name, stored_filename=stored_filename,
            file_type="docx", file_size=file_size, company_id=company_id,
        )
        db.set_kb_document_source(kb_doc["id"], source_type, source_id)
        kb_id = kb_doc["id"]

    db.mark_kb_pending(kb_id)
    process_document_async("kb", kb_id, file_path, "docx")
    return db.get_kb_document(kb_id)
