"""
services/retrieval_engine.py — Unified Intelligent Retrieval Engine for PharmaGPT v0.9.2.

Searches all available knowledge sources and returns the top-N most relevant
text chunks, ranked by multiple pharmaceutical domain signals.

Public API
----------
retrieve_context(document_type, project_id, equipment_name, questionnaire, max_chunks=10)
    → RetrievalResult

Architecture notes
------------------
The scoring backend is isolated in score_chunk(). To switch to vector embeddings
replace that one function with cosine_similarity(embed(chunk), embed(query)) —
the context-assembly, source-tracking, and RetrievalResult contract stay unchanged.

Sources searched
----------------
1. Project Documents       (document_text table)
2. Knowledge Base — SOPs   (kb_documents WHERE folder = 'SOP')
3. KB — Validation/Protocols
4. KB — Equipment Manuals  (folder = 'Vendor Documents')
5. KB — Regulations        (folder = 'Regulations')
6. KB — Other              (all remaining KB folders)
7. Previous Validation Docs (generated_documents table for this project)

Ranking signals (additive, all in score_chunk)
-----------------------------------------------
• Base keyword coverage    – Jaccard-style overlap between query tokens and chunk
• Equipment boost          – extra weight when chunk contains equipment name/model/mfr
• Document-type boost      – matches IQ/OQ/PQ aliases and related terms
• Regulatory/GMP boost     – recognised regulatory references (21 CFR, ICH, EU GMP …)
• Validation-term boost    – GxP vocabulary (qualification, protocol, CAPA, deviation …)
• Length bonus             – log-scale reward for longer chunks
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field

import database as db

logger = logging.getLogger(__name__)


# ── Pharmaceutical vocabulary boosters ────────────────────────────────────────

_REGULATORY_TERMS: frozenset[str] = frozenset({
    "21 cfr", "cfr 211", "cfr 820", "eu gmp", "ich q10", "ich q7", "ich q9",
    "ich q8", "fda", "ema", "iso 9001", "iso 13485", "usp", "ep", "bp",
    "21cfr", "part 11", "annex 11", "annex 15", "who", "pic/s",
})

_VALIDATION_TERMS: frozenset[str] = frozenset({
    "iq", "oq", "pq", "dq", "urs", "fmea", "capa", "fat", "sat",
    "qualification", "validation", "verification", "calibration",
    "gmp", "gxp", "glp", "gcp", "sop", "protocol", "deviation",
    "change control", "risk assessment", "installation", "operational",
    "performance", "acceptance criteria", "test case", "test result",
    "requalification", "periodic review", "alarm", "specification",
    "non-conformance", "corrective", "preventive", "traceability",
})

# Maps each doc_type to a set of recognition tokens for scoring boosts
_DOC_TYPE_ALIASES: dict[str, set[str]] = {
    "IQ":             {"iq", "installation", "installation qualification"},
    "OQ":             {"oq", "operational", "operational qualification"},
    "PQ":             {"pq", "performance", "performance qualification"},
    "URS":            {"urs", "user requirement", "requirements specification"},
    "DQ":             {"dq", "design", "design qualification"},
    "FAT":            {"fat", "factory acceptance", "factory acceptance test"},
    "SAT":            {"sat", "site acceptance", "site acceptance test"},
    "FMEA":           {"fmea", "failure mode", "effects analysis", "risk"},
    "CAPA":           {"capa", "corrective", "preventive", "corrective action"},
    "Deviation":      {"deviation", "non-conformance", "incident"},
    "Change Control": {"change control", "change management"},
}


# ── Source-type constants ─────────────────────────────────────────────────────

SOURCE_PROJECT_DOC   = "Project Document"
SOURCE_KB_SOP        = "SOP"
SOURCE_KB_VALIDATION = "Validation Protocol"
SOURCE_KB_EQUIPMENT  = "Equipment Manual"
SOURCE_KB_REGULATION = "Regulation"
SOURCE_KB_OTHER      = "Knowledge Base"
SOURCE_GENERATED_DOC = "Previous Validation Document"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RetrievedChunk:
    """Single retrieved text chunk with full source-traceability metadata."""
    text:          str
    doc_name:      str
    doc_type:      str          # one of the SOURCE_* constants above
    doc_id:        int | None
    page_number:   int | None   # None when page data unavailable
    section_title: str          # best-effort heading extracted from chunk start
    score:         float
    folder:        str = ""     # KB folder label, if applicable


@dataclass
class RetrievalResult:
    """
    Complete context package returned by retrieve_context().

    Attributes
    ----------
    context_text : formatted block ready to inject into the Gemini prompt
    chunks       : ordered list of top RetrievedChunk objects (for audit / UI)
    sources      : deduplicated [{id, name, doc_type}] list for citation UI
    found        : False when no relevant content was retrieved
    query_terms  : tokens used for scoring — kept for audit trail
    """
    context_text: str
    chunks:       list[RetrievedChunk]
    sources:      list[dict]
    found:        bool
    query_terms:  list[str]


# ── Text utilities ─────────────────────────────────────────────────────────────

def _tokenise(text: str) -> set[str]:
    """Lowercase, strip punctuation, return tokens longer than 2 characters."""
    return {
        w for w in re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
        if len(w) > 2
    }


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 60) -> list[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        c = " ".join(words[i: i + chunk_size])
        if c.strip():
            chunks.append(c)
    return chunks


def _extract_section_title(chunk: str) -> str:
    """
    Return the first non-empty line if it looks like a heading (< 80 chars).
    Used to populate RetrievedChunk.section_title for traceability.
    """
    first = chunk[:120].split("\n")[0].strip()
    return first if first and len(first) < 80 else ""


# ── Scoring engine ─────────────────────────────────────────────────────────────
# ┌──────────────────────────────────────────────────────────────────────────┐
# │ UPGRADE PATH TO VECTOR EMBEDDINGS                                        │
# │ Replace the body of score_chunk() with:                                  │
# │   return cosine_similarity(embed(chunk), query_vector)                   │
# │ No other changes required — RetrievalResult and context assembly         │
# │ are completely independent of the scoring method.                        │
# └──────────────────────────────────────────────────────────────────────────┘

def score_chunk(
    chunk: str,
    query_tokens: set[str],
    equipment_tokens: set[str],
    doc_type_tokens: set[str],
    boost_terms: frozenset[str],
) -> float:
    """
    Multi-signal relevance score for a single text chunk.

    Signals (additive):
      base_coverage   – Jaccard-style query-token overlap          (primary)
      equipment_boost – match on equipment name / model / mfr      (+0.30 max)
      doc_type_boost  – match on IQ/OQ/PQ aliases                  (+0.20 max)
      regulatory_boost– match on regulatory/validation vocabulary  (+0.25 max)
      length_bonus    – log-scale reward for richer context        (small)
    """
    if not query_tokens:
        return 0.0

    chunk_tokens = _tokenise(chunk)
    chunk_lower  = chunk.lower()

    # Base coverage
    matched      = len(query_tokens & chunk_tokens)
    base         = matched / (len(query_tokens) + 1)

    # Equipment boost
    equip_match  = len(equipment_tokens & chunk_tokens)
    equip_boost  = 0.30 * equip_match / max(len(equipment_tokens), 1) if equipment_tokens else 0.0

    # Document-type alias boost
    dtype_match  = len(doc_type_tokens & chunk_tokens)
    dtype_boost  = 0.20 * dtype_match / max(len(doc_type_tokens), 1) if doc_type_tokens else 0.0

    # Regulatory / validation-term boost (count occurrences, cap at 5)
    reg_hits     = sum(1 for t in boost_terms if t in chunk_lower)
    reg_boost    = 0.05 * min(reg_hits, 5)

    # Length bonus
    length_bonus = math.log(max(len(chunk.split()), 1)) / 100

    return base + equip_boost + dtype_boost + reg_boost + length_bonus


# ── Internal data loaders ─────────────────────────────────────────────────────

def _load_project_docs(project_id: int) -> list[dict]:
    return db.get_all_document_texts(project_id)


def _load_kb_all() -> list[dict]:
    """Return all KB rows that have successfully extracted text."""
    conn = db.get_connection()
    rows = conn.execute(
        """SELECT id, title, folder, tags, original_name, text_content, page_count
           FROM kb_documents
           WHERE extraction_status = 'ok'
             AND text_content IS NOT NULL
             AND text_content != ''
           ORDER BY upload_date DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _load_generated_docs(project_id: int) -> list[dict]:
    """Return metadata rows (no content) for previously generated docs."""
    return db.get_project_generated_documents(project_id)


def _get_generated_content(doc_id: int) -> str:
    row = db.get_generated_document(doc_id)
    return (row.get("content") or "") if row else ""


def _folder_to_source_type(folder: str) -> str:
    f = (folder or "").lower().strip()
    if f == "sop":
        return SOURCE_KB_SOP
    if f in ("validation", "protocols", "qualification"):
        return SOURCE_KB_VALIDATION
    if f in ("vendor documents", "vendor", "equipment"):
        return SOURCE_KB_EQUIPMENT
    if f in ("regulations", "regulatory"):
        return SOURCE_KB_REGULATION
    return SOURCE_KB_OTHER


# ── Main retrieval function ────────────────────────────────────────────────────

def retrieve_context(
    document_type: str,
    project_id: int,
    equipment_name: str = "",
    questionnaire: dict | None = None,
    max_chunks: int = 10,
) -> RetrievalResult:
    """
    Retrieve the top-N most relevant text chunks from all knowledge sources.

    The result is cached implicitly within a single request because this
    function is called once per document generation — callers should not
    invoke it more than once for the same generation.

    Parameters
    ----------
    document_type  : "IQ" | "OQ" | "PQ" | "URS" | "DQ" | "FAT" | "SAT" |
                     "FMEA" | "CAPA" | "Deviation" | "Change Control"
    project_id     : active project ID
    equipment_name : concatenation of equipment_name + model + manufacturer
                     from form_data (used for relevance boosting)
    questionnaire  : form_data["details"] dict — values are mined for query tokens
    max_chunks     : maximum chunks in the returned context package (default 10)

    Returns
    -------
    RetrievalResult
    """
    if questionnaire is None:
        questionnaire = {}

    # ── Build composite query ──────────────────────────────────────────────────
    q_parts = [document_type, equipment_name]
    q_parts += [
        str(v)
        for v in questionnaire.values()
        if isinstance(v, (str, int, float)) and str(v).strip()
    ]
    query_tokens     = _tokenise(" ".join(q_parts))
    equipment_tokens = _tokenise(equipment_name)
    dtype_aliases    = _DOC_TYPE_ALIASES.get(document_type, set())
    doc_type_tokens  = dtype_aliases | _tokenise(document_type)
    boost_terms      = _REGULATORY_TERMS | _VALIDATION_TERMS

    all_chunks: list[RetrievedChunk] = []

    # ── Source 1 : Project Documents ──────────────────────────────────────────
    try:
        for row in _load_project_docs(project_id):
            text = row.get("text_content", "")
            if not text.strip():
                continue
            for chunk in chunk_text(text):
                s = score_chunk(chunk, query_tokens, equipment_tokens,
                                doc_type_tokens, boost_terms)
                if s > 0:
                    all_chunks.append(RetrievedChunk(
                        text=chunk,
                        doc_name=row["original_name"],
                        doc_type=SOURCE_PROJECT_DOC,
                        doc_id=row["document_id"],
                        page_number=None,
                        section_title=_extract_section_title(chunk),
                        score=s,
                    ))
    except Exception:
        logger.exception("retrieval_engine: error scanning project documents")

    # ── Source 2–6 : Knowledge Base ───────────────────────────────────────────
    try:
        for row in _load_kb_all():
            text = row.get("text_content", "")
            if not text.strip():
                continue
            folder   = row.get("folder", "Others")
            src_type = _folder_to_source_type(folder)
            title    = row.get("title") or row.get("original_name", "KB Document")
            for chunk in chunk_text(text):
                s = score_chunk(chunk, query_tokens, equipment_tokens,
                                doc_type_tokens, boost_terms)
                if s > 0:
                    all_chunks.append(RetrievedChunk(
                        text=chunk,
                        doc_name=title,
                        doc_type=src_type,
                        doc_id=row["id"],
                        page_number=None,
                        section_title=_extract_section_title(chunk),
                        score=s,
                        folder=folder,
                    ))
    except Exception:
        logger.exception("retrieval_engine: error scanning knowledge base")

    # ── Source 7 : Previously Generated Validation Documents ──────────────────
    try:
        for meta in _load_generated_docs(project_id):
            content = _get_generated_content(meta["id"])
            if not content.strip():
                continue
            gen_title = meta.get("title") or f"{meta.get('doc_type', 'DOC')} Document"
            for chunk in chunk_text(content):
                s = score_chunk(chunk, query_tokens, equipment_tokens,
                                doc_type_tokens, boost_terms)
                if s > 0:
                    all_chunks.append(RetrievedChunk(
                        text=chunk,
                        doc_name=gen_title,
                        doc_type=SOURCE_GENERATED_DOC,
                        doc_id=meta["id"],
                        page_number=None,
                        section_title=_extract_section_title(chunk),
                        score=s,
                    ))
    except Exception:
        logger.exception("retrieval_engine: error scanning generated documents")

    if not all_chunks:
        return RetrievalResult(
            context_text="",
            chunks=[],
            sources=[],
            found=False,
            query_terms=sorted(query_tokens),
        )

    # Sort descending by score, keep top max_chunks
    all_chunks.sort(key=lambda c: c.score, reverse=True)
    top = all_chunks[:max_chunks]

    context_text = _build_context_package(top, document_type, equipment_name)

    # Deduplicated source list for citation UI
    seen: dict[tuple, dict] = {}
    for c in top:
        key = (c.doc_type, c.doc_id)
        if key not in seen:
            seen[key] = {"id": c.doc_id, "name": c.doc_name, "doc_type": c.doc_type}
    sources = list(seen.values())

    return RetrievalResult(
        context_text=context_text,
        chunks=top,
        sources=sources,
        found=True,
        query_terms=sorted(query_tokens),
    )


# ── Context package builder ────────────────────────────────────────────────────

_SECTION_ORDER = [
    SOURCE_PROJECT_DOC,
    SOURCE_KB_SOP,
    SOURCE_KB_VALIDATION,
    SOURCE_KB_EQUIPMENT,
    SOURCE_KB_REGULATION,
    SOURCE_KB_OTHER,
    SOURCE_GENERATED_DOC,
]

_SECTION_HEADERS = {
    SOURCE_PROJECT_DOC:      "RELEVANT PROJECT DOCUMENT SECTIONS",
    SOURCE_KB_SOP:           "RELEVANT SOP SECTIONS",
    SOURCE_KB_VALIDATION:    "VALIDATION PROTOCOLS & QUALIFICATION REFERENCES",
    SOURCE_KB_EQUIPMENT:     "EQUIPMENT MANUAL SECTIONS",
    SOURCE_KB_REGULATION:    "APPLICABLE REGULATIONS",
    SOURCE_KB_OTHER:         "KNOWLEDGE BASE MATCHES",
    SOURCE_GENERATED_DOC:    "PREVIOUS VALIDATION DOCUMENTS",
}


def _build_context_package(
    chunks: list[RetrievedChunk],
    document_type: str,
    equipment_name: str,
) -> str:
    """
    Organise retrieved chunks into a structured, GMP-annotated context block.

    Each chunk carries a traceability header:
      [Source: <doc_name> | Type: <doc_type> | Section: <title> | Relevance: <score>]

    Sections are ordered by knowledge-source priority so the LLM sees the
    most authoritative context first.
    """
    by_type: dict[str, list[RetrievedChunk]] = {}
    for c in chunks:
        by_type.setdefault(c.doc_type, []).append(c)

    lines: list[str] = [
        "=== RETRIEVED KNOWLEDGE CONTEXT ===",
        f"Document Type: {document_type} | Equipment: {equipment_name}",
        "Use this retrieved information to generate an accurate, GMP-compliant document.",
        "Cite specific documents by name where they informed your content.",
        "",
    ]

    for src_type in _SECTION_ORDER:
        section_chunks = by_type.get(src_type, [])
        if not section_chunks:
            continue

        lines.append(f"--- {_SECTION_HEADERS[src_type]} ---")
        lines.append("")

        for c in section_chunks:
            meta_parts = [f"Source: {c.doc_name}", f"Type: {c.doc_type}"]
            if c.section_title:
                meta_parts.append(f"Section: {c.section_title[:60]}")
            if c.page_number is not None:
                meta_parts.append(f"Page: {c.page_number}")
            meta_parts.append(f"Relevance: {c.score:.3f}")

            lines.append(f"[{' | '.join(meta_parts)}]")
            lines.append(c.text)
            lines.append("")

    lines.append("=== END RETRIEVED CONTEXT ===")
    return "\n".join(lines)
