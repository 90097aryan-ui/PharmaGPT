"""
services/document_search.py — Relevance search over extracted document text.

Architecture — v0.5 (keyword-based):
──────────────────────────────────────
1. Split each document's extracted text into overlapping chunks (~400 words).
2. Score each chunk against the user's query using keyword overlap (TF-IDF-like).
3. Return the top-k chunks, tagged with their source document name and id.
4. Assemble a formatted context block to inject into the Gemini prompt.

Architecture — v0.6+ (RAG / vector-based, stubs below):
──────────────────────────────────────────────────────────
Replace score_chunk() with:
  - generate_embedding(text) → vector  (Gemini Embeddings or Sentence Transformers)
  - upsert_to_vector_store(doc_id, chunks, vectors)  (ChromaDB / FAISS / Pinecone)
  - vector_search(query_vector, top_k) → [(chunk, doc_id, score)]

The rest of the pipeline (context assembly, source tracking) stays the same.
"""

import re
import math
import database as db


# ── Text chunking ─────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 400, overlap: int = 60) -> list[str]:
    """
    Split text into overlapping word-based chunks.

    overlap ensures that sentences spanning a chunk boundary are not lost.

    Parameters
    ----------
    text       : full document text
    chunk_size : words per chunk
    overlap    : words shared between consecutive chunks

    Returns
    -------
    list of text chunks (strings)
    """
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    step = max(1, chunk_size - overlap)

    for i in range(0, len(words), step):
        chunk = " ".join(words[i: i + chunk_size])
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
    Score a chunk against query tokens.

    Uses a simple Jaccard-like overlap weighted by query coverage:
        score = (matched_query_tokens) / (total_query_tokens + 1)

    Also applies a small length penalty so very short chunks score lower.

    v0.6+: Replace with cosine similarity between embedding vectors.
    """
    if not query_tokens:
        return 0.0
    chunk_tokens = _tokenise(chunk)
    matched = len(query_tokens & chunk_tokens)
    coverage = matched / (len(query_tokens) + 1)
    # Small bonus for longer chunks (more context is better)
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
    query             : the user's chat message
    project_id        : project to search within
    top_k             : maximum number of chunks to include
    max_context_words : hard cap on total words in the returned context

    Returns
    -------
    dict with keys:
        context_text : str  — formatted block to prepend to the Gemini prompt
        sources      : list[dict]  — [{id, name}] of cited documents (deduplicated)
        found        : bool — False if no relevant content was found
    """
    # Load all extracted texts for the project (joined with document names)
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

    # Enforce max_context_words budget
    context_parts: list[str] = []
    sources_seen: dict[int, str] = {}   # doc_id → doc_name (ordered, deduped)
    total_words = 0

    for _score, chunk, doc_id, doc_name in selected:
        chunk_words = len(chunk.split())
        if total_words + chunk_words > max_context_words:
            # Truncate the chunk to fit within budget
            remaining = max_context_words - total_words
            if remaining < 50:
                break
            chunk = " ".join(chunk.split()[:remaining])
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


# ── v0.6+ RAG stubs ───────────────────────────────────────────────────────────

def generate_embedding(text: str, gemini_client) -> list[float]:
    """
    Stub: Generate a vector embedding for a text chunk.
    v0.6+: Call gemini_client.models.embed_content() or Sentence Transformers.
    """
    raise NotImplementedError("Vector embeddings will be implemented in v0.6")


def upsert_to_vector_store(doc_id: int, chunks: list[str], vectors: list[list[float]]):
    """
    Stub: Store embeddings in a vector database (ChromaDB / FAISS / Pinecone).
    v0.6+: Implement with chromadb.Client().get_or_create_collection(...).
    """
    raise NotImplementedError("Vector store upsert will be implemented in v0.6")


def vector_search(query_vector: list[float], project_id: int, top_k: int = 5):
    """
    Stub: Retrieve top-k semantically similar chunks from the vector store.
    v0.6+: Replace score_chunk() keyword matching with this call.
    """
    raise NotImplementedError("Vector search will be implemented in v0.6")
