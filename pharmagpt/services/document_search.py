"""
services/document_search.py — Relevance search over extracted document text.

Keyword-based RAG pipeline (v0.5+)
-----------------------------------
1. Load all extracted texts for the project from the database.
2. Split each document into overlapping word-based chunks (~400 words).
3. Score each chunk against the query using keyword overlap (Jaccard-style).
4. Return the top-k chunks, tagged with their source document name and id.
5. Assemble a formatted context block ready to inject into the Gemini prompt.

Planned upgrade (v0.8)
-----------------------
Replace score_chunk() with semantic vector search:
  - generate_embedding(text) → vector  (Gemini Embeddings API)
  - store vectors in a new document_embeddings table or ChromaDB
  - cosine_similarity(query_vector, chunk_vector) replaces Jaccard scoring
The context-assembly and source-tracking logic below stays unchanged.
"""

import re
import math
from pharmagpt import database as db


# ── Text chunking ─────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 400, overlap: int = 60) -> list[str]:
    """
    Split text into overlapping word-based chunks.

    overlap ensures sentences that span a chunk boundary are not lost.

    Parameters
    ----------
    text       : full document text
    chunk_size : words per chunk
    overlap    : words shared between consecutive chunks

    Returns
    -------
    list of non-empty text chunks
    """
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    step = max(1, chunk_size - overlap)

    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)

    return chunks


# ── Keyword scoring ───────────────────────────────────────────────────────────

def _tokenise(text: str) -> set[str]:
    """Lowercase, strip punctuation, return a set of tokens longer than 2 chars."""
    return {
        w for w in re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
        if len(w) > 2
    }


def score_chunk(chunk: str, query_tokens: set[str]) -> float:
    """
    Score a chunk against query tokens using Jaccard-style keyword overlap.

        score = matched_query_tokens / (total_query_tokens + 1)

    A small length bonus rewards longer chunks — more context is generally
    more useful when injected into a Gemini prompt.

    Returns 0.0 if query_tokens is empty.
    """
    if not query_tokens:
        return 0.0
    chunk_tokens = _tokenise(chunk)
    matched      = len(query_tokens & chunk_tokens)
    coverage     = matched / (len(query_tokens) + 1)
    length_bonus = math.log(max(len(chunk.split()), 1)) / 100
    return coverage + length_bonus


# ── Main search function ──────────────────────────────────────────────────────

def search_project_documents(
    query: str,
    project_id: int,
    top_k: int = 5,
    max_context_words: int = 2500,
) -> dict:
    """
    Search all extracted texts for a project and return the most relevant
    chunks plus a formatted context block ready to inject into Gemini.

    Parameters
    ----------
    query             : the user's chat message or generation query
    project_id        : project to search within
    top_k             : maximum number of chunks to include
    max_context_words : hard cap on total words in the returned context block

    Returns
    -------
    dict with keys:
        context_text : str        — formatted block to prepend to the Gemini prompt
        sources      : list[dict] — [{id, name}] of cited documents (deduplicated)
        found        : bool       — False if no relevant content was found
    """
    rows = db.get_all_document_texts(project_id)

    if not rows:
        return {"context_text": "", "sources": [], "found": False}

    query_tokens = _tokenise(query)

    # Score every chunk from every document
    scored: list[tuple[float, str, int, str]] = []  # (score, chunk, doc_id, doc_name)

    for row in rows:
        doc_id   = row["document_id"]
        doc_name = row["original_name"]
        text     = row["text_content"]

        if not text.strip():
            continue

        for chunk in chunk_text(text):
            s = score_chunk(chunk, query_tokens)
            if s > 0:
                scored.append((s, chunk, doc_id, doc_name))

    if not scored:
        return {"context_text": "", "sources": [], "found": False}

    # Sort by descending score, take top_k
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = scored[:top_k]

    # Enforce the word-count budget, truncating the last chunk if needed
    context_parts: list[str]    = []
    sources_seen:  dict[int, str] = {}   # doc_id → doc_name (ordered, deduped)
    total_words = 0

    for _score, chunk, doc_id, doc_name in selected:
        chunk_words = len(chunk.split())
        if total_words + chunk_words > max_context_words:
            remaining = max_context_words - total_words
            if remaining < 50:   # not worth including a very short tail fragment
                break
            chunk       = " ".join(chunk.split()[:remaining])
            chunk_words = remaining

        context_parts.append(f"[Source: {doc_name}]\n{chunk}")
        sources_seen[doc_id] = doc_name
        total_words += chunk_words

    context_text = (
        "=== DOCUMENT CONTEXT ===\n"
        "The following content was extracted from the project's uploaded documents.\n"
        "Use this information to answer the user's question.\n"
        "Always cite which document(s) your answer is based on.\n\n"
        + "\n\n".join(context_parts)
        + "\n=== END DOCUMENT CONTEXT ===\n\n"
    )

    sources = [{"id": doc_id, "name": name} for doc_id, name in sources_seen.items()]

    return {"context_text": context_text, "sources": sources, "found": True}
