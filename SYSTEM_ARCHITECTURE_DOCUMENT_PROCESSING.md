# PharmaGPT — Enterprise Document Processing Engine

**Status:** v1.0 · Replaces the synchronous pdfplumber-only extraction path entirely (no code from `services/extractor.py` / `services/pdf_reader.py` was reused — both files have been deleted).

## 1. Why this exists

Production upload of a real 48-page / 1.43 MB ACMI pharmaceutical labeller manual on Render caused:

```
Knowledge Base Upload
  -> extractor.py
  -> pdf_reader.py
  -> pdfplumber.page.extract_text()
  -> Worker Timeout
  -> SIGKILL
  -> HTTP 500
```

Root cause: the entire PDF was parsed by a single library, synchronously, inside the HTTP request thread, with no timeout, no fallback, and no memory management. PharmaGPT's actual document corpus — vendor manuals, IQ/OQ/PQ protocols, validation reports, URS, FAT/SAT, SOPs, SCADA/PLC manuals, engineering drawings — includes documents exceeding 1000 pages. That architecture cannot survive in production. It has been replaced, not patched.

## 2. Architecture at a glance

```
                         ┌───────────────────────────────────────────┐
                         │        routes/docs.py, routes/            │
                         │        knowledge_base.py  (HTTP layer)    │
                         └───────────────┬─────────────────────────--┘
                                         │ save file, create "pending" row,
                                         │ return HTTP 201 immediately
                                         ▼
                         ┌───────────────────────────────────────────┐
                         │   services/document_processor.py          │
                         │   (THE single entry point)                │
                         │                                            │
                         │   process_document_async(kind, id, ...)   │
                         │        │                                   │
                         │        ▼                                   │
                         │   services/job_runner.py (Strategy)        │
                         │   ThreadPoolJobRunner.submit(...)          │
                         └───────────────┬─────────────────────────--┘
                                         │ background thread
                                         ▼
                         ┌───────────────────────────────────────────┐
                         │   services/extraction/pipeline.py          │
                         │   extract_document(file, engines, ...)     │
                         │                                            │
                         │   for page in 0..N:                        │
                         │     try primary engine (timeout-bounded)   │
                         │       -> on fail/timeout: try next engine  │
                         │       -> on all-fail: log + skip page      │
                         │     progress_cb(page, total) every page    │
                         │     every K pages: drop caches + gc.collect │
                         └───────────────┬─────────────────────────--┘
                                         │ ExtractionResult
                                         ▼
                         ┌───────────────────────────────────────────┐
                         │   database.py                              │
                         │   document_text / kb_documents rows        │
                         │   status: pending -> processing -> ok |    │
                         │           partial | empty | failed         │
                         └───────────────┬─────────────────────────--┘
                                         │ polled by
                                         ▼
                         ┌───────────────────────────────────────────┐
                         │  static/js/documents.js, knowledge_base.js │
                         │  setInterval poll /status every 1.5s       │
                         │  "Extracting page N/Total…" -> badge       │
                         │  Retry Extraction button on failure        │
                         └───────────────────────────────────────────┘
```

Chat / RAG / URS / Qualification / Validation Reports / Risk Management all read `document_text.text_content` / `kb_documents.text_content` through the *existing* `retrieval_engine.py` and `document_search.py`, which already filter on `extraction_status = 'ok'`. They required **zero code changes** — a document simply becomes visible to them the moment its background extraction finishes, instead of always being visible immediately (which was only true because extraction used to block the upload).

## 3. File structure

```
pharmagpt/
  logging_config.py                  structured logging setup, called once from app.py
  services/
    document_processor.py            single entry point: extract_sync() + process_document_async()
    job_runner.py                    Strategy: JobRunner / ThreadPoolJobRunner / CeleryJobRunner (stub)
    extraction/
      base.py                        ExtractionEngine interface (Strategy pattern)
      pdf_engines.py                 PyPDFEngine, PdfplumberEngine, PyMuPDFEngine, OCRPlaceholderEngine
      simple_engines.py              DocxEngine, ExcelEngine, TxtEngine (wrap existing readers)
      registry.py                    extension -> ordered engine list
      pipeline.py                    page-by-page loop: fallback, timeout, memory management
      stats.py                       ExtractionResult dataclass + quality_score()
    docx_reader.py, excel_reader.py  unchanged — reused by simple_engines.py
  database.py                        additive schema + CRUD for progress/status/retry
  routes/docs.py, knowledge_base.py  async upload + /status + /retry endpoints
tests/
  conftest.py, fixtures/generate_fixtures.py
  test_pdf_engines.py, test_pipeline.py, test_document_processor.py,
  test_job_runner.py, test_routes_upload_async.py
```

Nothing outside `services/extraction/` imports `pdfplumber`, `pypdf`, or `fitz` directly.

## 4. Engine selection & fallback logic

Priority order per extension, defined in `services/extraction/registry.py`:

| Extension | Engine chain |
|---|---|
| `pdf`  | `pypdf` → `pdfplumber` → `pymupdf` → `ocr_placeholder` |
| `docx` | `python-docx` (existing `docx_reader.py`, unchanged) |
| `xlsx` | `openpyxl` (existing `excel_reader.py`, unchanged) |
| `txt`  | plain read |

Selection happens twice, at two granularities:

1. **Document-level (which engine opens the file):** engines are tried in order until one succeeds. A corrupted or password-protected file fails every engine's `open()` — the document is still stored, marked `status="failed"`, and can be retried later; nothing raises out of the pipeline.
2. **Page-level (fallback while iterating):** if the *primary* engine fails or times out on a specific page, the pipeline lazily opens the next engine in the chain (once, cached for the rest of the document — never re-reads the whole file per page) and retries just that page. If every engine fails that page, it is logged and skipped; the document continues.

```
PyPDF fails page 17
   -> pdfplumber (already open, or opened now) tries page 17
       -> pdfplumber times out
           -> PyMuPDF tries page 17
               -> also fails
                   -> log "Page 17 failed on all engines" -> skip -> continue
```

`OCRPlaceholderEngine` is always last in the PDF chain and always raises — it exists so scanned/image-only content is clearly attributed to "OCR not yet available" in `page_errors`, and so adding a real OCR backend later is a one-class change (see §8).

## 5. Timeout protection

Each attempt (`engine.extract_page(handle, index)`) runs in its own daemon thread, joined with `PAGE_TIMEOUT_SECONDS` (default 10s, `config.py`). **Each attempt gets a fresh thread** rather than a shared pool — an earlier version used one shared single-worker thread pool and had a real bug: a hung primary-engine call occupied the pool's only worker, so the *fallback* engine's attempt on the same page was starved too (queued behind the same stuck worker) and also "timed out". Per-attempt threads fix this; `tests/test_pipeline.py::test_page_timeout_falls_back_and_never_blocks_document` guards the regression.

**Known limitation:** CPython cannot forcibly kill a running thread. A timed-out call is *abandoned*, not terminated — the pipeline stops waiting and moves on, and the orphaned thread finishes (or hangs forever, harmlessly) in the background as a daemon. This bounds worst-case wall-clock time per document without risking corrupted engine state from a hard kill. If a specific library is found to hang indefinitely in production, the next step is a subprocess pool (true OS-level termination via `process.terminate()`), which the `ExtractionEngine` interface does not preclude — see the roadmap.

## 6. Memory management

- Pages are processed one at a time — the pipeline never loads a page list or the full document text into one structure until the final `"\n\n".join(texts)` at the end.
- `pdfplumber` pages call `page.flush_cache()` immediately after `extract_text()` — otherwise pdfplumber accumulates per-page char/word/line caches indefinitely, which is the classic memory-growth pattern on large PDFs.
- `PyMuPDF` pages are dereferenced (`page = None`) immediately after use.
- Every `GC_INTERVAL_PAGES` (default 20) pages, `gc.collect()` runs explicitly.
- All engine handles are closed in a `finally` block, and a final `gc.collect()` runs after the document completes, regardless of success or failure.

## 7. Extraction statistics & quality score

`services/extraction/stats.py::ExtractionResult` — returned by every extraction, always:

| Field | Meaning |
|---|---|
| `document_name` | filename |
| `page_count` | real page count (PDF) or a display estimate (DOCX/XLSX/TXT) |
| `pages_extracted` / `pages_failed` | per-page success/failure counts |
| `word_count` | words in the combined extracted text |
| `extraction_time_seconds` | wall-clock duration |
| `engine_used` | the engine that handled the most pages |
| `quality_score` | `pages_extracted / page_count * 100`, rounded to 1 decimal; `0.0` if `page_count == 0` |
| `status` | `ok` \| `partial` \| `empty` \| `failed` |
| `page_errors` | `[{page, error}]` for anything skipped |

Example: 48 pages, 46 extracted, 2 skipped → quality score `95.8`.

## 8. Database changes (additive only)

`database.py::init_db()` adds columns via a `PRAGMA table_info()`-guarded helper (`_add_column_if_missing`) — never drops or renames anything:

`document_text` and `kb_documents` gain: `extraction_progress_current`, `extraction_progress_total`, `extraction_engine`, `quality_score`, `extraction_seconds`, `pages_failed`, `error_message`.

`extraction_status` gains new values used by the async pipeline — `pending`, `processing`, `partial`, `failed` — alongside the pre-existing `ok` \| `empty` \| `error`. `retrieval_engine.py`'s `WHERE extraction_status = 'ok'` filter needed **no changes**: new intermediate/failure states are simply excluded automatically.

## 9. API surface

| Method & path | Purpose |
|---|---|
| `POST /projects/<id>/documents` | Upload — saves file, creates a `pending` row, submits background job, returns `201` immediately |
| `GET /documents/<id>/status` | Poll `{extraction_status, extraction_progress_current/total, extraction_engine, quality_score, pages_failed, page_count, word_count, error_message}` |
| `POST /documents/<id>/retry` | Re-run extraction in place (file is never deleted) |
| `POST /kb/documents` | Same async pattern for Knowledge Base uploads |
| `GET /kb/documents/<id>/status` | Same status shape for KB |
| `POST /kb/documents/<id>/retry` | Same retry semantics for KB |

Frontend (`documents.js`, `knowledge_base.js`) polls `/status` every 1.5s after upload, renders "Extracting page N/Total…", switches to a quality/failure badge on completion, and shows a **Retry Extraction** button when status is `failed`/`error`/`partial`.

## 10. Background execution (why ThreadPoolExecutor, not Celery)

Confirmed with the product owner: the current stack is Flask + gunicorn + SQLite on Render, with no Redis/Celery. Introducing them now would mean a new managed service, a new worker dyno, and new deployment complexity — a deliberate infrastructure decision, not something to smuggle into an extraction refactor.

`services/job_runner.py` defines a `JobRunner` Strategy interface. `ThreadPoolJobRunner` (in-process `concurrent.futures.ThreadPoolExecutor`, size `EXTRACTION_WORKERS`) is the active implementation. All progress and results are persisted to SQLite — never held only in memory — so status polling works correctly regardless of which gunicorn worker process happens to handle a given poll request. `CeleryJobRunner` is a documented, unimplemented stub: swapping to Celery + Redis later is implementing one class and changing the module-level `job_runner = ...` line — no route or business logic changes anywhere else.

## 11. Performance (measured on this machine, Python 3.14.6)

| Fixture | Pages | Result | Time |
|---|---|---|---|
| `small.pdf` | 5 | ok, 100% quality | ~0.3s |
| `large.pdf` | 200 | ok, 100% quality | ~0.7s |
| 1000-page stress fixture | 1000 | ok, 100% quality | ~9s |

Both named targets (100 pages < 20s, 200 pages < 40s) are met with large margin using the `pypdf` primary engine on clean text PDFs; fallback engines only activate — at a per-page cost — when the primary engine fails or times out.

## 12. Testing

`tests/fixtures/generate_fixtures.py` builds every fixture with PyMuPDF only (already a production dependency — no extra test-only library): `small.pdf`, `large.pdf` (200p), `scanned.pdf` (image-only, no text layer), `mixed.pdf` (alternating text/image pages), `engineering_manual.pdf`, `empty.pdf`, `corrupted.pdf` (truncated bytes), `password_protected.pdf` (real AES-256 encryption with a non-empty password). A `@pytest.mark.slow` test builds a 1000-page fixture on demand (`pytest -m slow`).

- `test_pdf_engines.py` — each engine in isolation (open/page_count/extract_page/close), including DOCX/XLSX/TXT single-loop-unit adapters.
- `test_pipeline.py` — fallback, per-page timeout (with the shared-pool regression test), skip-and-continue, gc interval, quality score formula — using fake in-memory engines for speed and determinism.
- `test_document_processor.py` — `extract_sync()` end-to-end over every fixture, plus the performance targets.
- `test_job_runner.py` — `ThreadPoolJobRunner` execution and crash isolation.
- `test_routes_upload_async.py` — Flask test client: fast upload response, status polling to a terminal state, retry flow, 404 handling, file-missing-on-retry handling. Each test runs against an isolated throwaway SQLite file (`tests/conftest.py::db_path`) — the real development database is never touched.

Run: `pip install -r requirements-dev.txt && pytest` (41 tests, ~11s; add `-m slow` for the 1000-page stress test).

## 13. Backward compatibility

Every consumer of extracted text — `services/retrieval_engine.py`, `services/document_search.py`, and by extension `routes/chat.py`, `routes/validation.py`, URS, Qualification, and Risk Management — reads `document_text` / `kb_documents` rows exactly as before, filtered on `extraction_status = 'ok'`. None of them needed to change. The only behavioral difference: a just-uploaded, still-extracting document is briefly invisible to search/RAG instead of always being present — which is the correct tradeoff for a system that no longer blocks the HTTP response on extraction.

## 14. Future roadmap

- **Real OCR** for scanned/image-only pages: implement `ExtractionEngine` around `pytesseract` (or a cloud OCR API) and register it in `registry.py`'s `ENGINES["pdf"]` list in place of `OCRPlaceholderEngine`.
- **Cloud document intelligence** (Azure Document Intelligence / AWS Textract / Google Document AI): each is a new `ExtractionEngine` subclass — `open()` uploads/calls the API, `extract_page()` returns that page's text from the API response. No pipeline, route, or database change required.
- **Celery + Redis**: implement `CeleryJobRunner.submit()` and point the `job_runner` singleton at it. Progress/status persistence already lives in SQLite (or a future Postgres), so this is a pure execution-backend swap.
- **True per-page process isolation**: if a specific PDF is found to hang a thread indefinitely in production, move `_run_with_timeout` in `pipeline.py` to a `ProcessPoolExecutor` so a stuck attempt can be `terminate()`-d rather than merely abandoned.
- **Password-protected PDF support**: currently these are marked `failed` (empty-password attempt only). A future version could accept a user-supplied password on upload/retry and pass it through `ExtractionEngine.open()`.
