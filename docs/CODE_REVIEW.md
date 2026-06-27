# Code Review — PharmaGPT

**Version:** 1.0  
**Date:** 2026-06-27  
**Reviewer:** Claude Sonnet 4.6  
**Scope:** Full codebase audit — v0.7 (Knowledge Base release)  
**Status:** Findings only — no code modified

---

## Summary

| Category | Count | Highest Severity |
|----------|-------|-----------------|
| Security issues | 6 | Critical |
| Duplicate code | 3 | Medium |
| Dead code / stubs | 7 | Medium |
| Unused API routes | 2 | Low |
| Performance issues | 5 | High |
| UI inconsistencies | 5 | Medium |
| Unused CSS | 2 | Low |
| Unused JS | 2 | Low |

Severity scale: **Critical → High → Medium → Low → Info**

---

## 1. Security Issues

### 1.1 XSS — Unescaped Markdown Rendered as HTML
**Severity: Critical**  
**Files:** `static/js/chat.js:47`, `static/js/chat.js:221`

AI responses and streaming content are rendered directly via `innerHTML` after being parsed by `marked.js`, with no sanitization layer:

```javascript
// chat.js:47 — completed message bubble
bubble.innerHTML = marked.parse(text);

// chat.js:221 — streaming token accumulation
contentEl.innerHTML = marked.parse(accumulatedText);
```

If the Gemini API is ever compromised, returns an adversarial response, or if a document injected via RAG contains a crafted payload, a script could execute in the user's browser. `marked.js` does not sanitize HTML by default.

**Fix:** Wrap all `marked.parse()` output with DOMPurify before assigning to `innerHTML`:
```javascript
contentEl.innerHTML = DOMPurify.sanitize(marked.parse(accumulatedText));
```

---

### 1.2 Hardcoded Fallback Secret Key
**Severity: Critical**  
**File:** `pharmagpt/config.py:15`

```python
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "pharmagpt-dev-secret-key")
```

If `.env` is missing or `FLASK_SECRET_KEY` is not set, Flask silently uses the predictable string `"pharmagpt-dev-secret-key"` to sign session cookies. An attacker who knows this value (it is in the source code) can forge valid session cookies.

**Fix:** Fail loudly if the key is absent instead of falling back:
```python
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
    raise RuntimeError("FLASK_SECRET_KEY is not set. Add it to .env.")
```

---

### 1.3 No CSRF Protection on State-Modifying Routes
**Severity: High**  
**File:** `pharmagpt/app.py` (all POST/DELETE routes)

Flask-WTF CSRF protection is not configured. Any POST or DELETE endpoint — including `/projects`, `/stream`, `/validation/save`, `/kb/documents`, `/documents/<id>` — can be triggered by a malicious third-party page if the user is browsing while the app is running. This is a cross-site request forgery vulnerability.

**Fix:** Install `flask-wtf` and initialise CSRF:
```python
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)
```
Then include the CSRF token in all fetch calls from JavaScript:
```javascript
headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() }
```

---

### 1.4 Silent Exception Swallowing in Text Extraction
**Severity: High**  
**File:** `pharmagpt/app.py:295`, `pharmagpt/app.py:654`

Both `_extract_and_store()` and `_extract_and_store_kb()` catch all exceptions with a bare `except Exception:` and store an error status silently:

```python
# app.py:295
except Exception:
    db.save_document_text(doc_id, project_id, "", 0, 0, "error")

# app.py:654
except Exception:
    db.update_kb_document_text(kb_id, "", 0, 0, "error")
```

There is no logging, no error message to the user, and no way to distinguish a corrupt file from a disk-full condition or a bug in the extraction library. In practice, users have no indication that their document failed to extract and will receive no AI context from it.

**Fix:** At minimum, log the exception:
```python
except Exception as exc:
    import logging
    logging.getLogger(__name__).error("Extraction failed for doc %s: %s", doc_id, exc)
    db.save_document_text(doc_id, project_id, "", 0, 0, "error")
```

---

### 1.5 No Rate Limiting on Expensive Endpoints
**Severity: High**  
**File:** `pharmagpt/app.py:115` (`/stream`), `pharmagpt/app.py:375` (`/validation/generate`)

Both streaming endpoints call the Gemini API with no throttling. A single user — or a script — can fire unlimited concurrent requests, burning through the API quota instantly and potentially causing significant cost. There is no per-IP or per-session limit.

**Fix:** Use `flask-limiter`:
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
limiter = Limiter(app, key_func=get_remote_address)

@app.route("/stream", methods=["POST"])
@limiter.limit("20 per minute")
def stream(): ...
```

---

### 1.6 `session_id` Assigned But Never Used
**Severity: Low**  
**File:** `pharmagpt/app.py:50-51`

```python
if "session_id" not in session:
    session["session_id"] = str(uuid.uuid4())
```

A UUID is generated and stored in the Flask session on every first visit, but it is never read anywhere else in the codebase. This contributes nothing and is misleading — it implies session-based isolation that does not exist. All project data is globally readable by anyone.

**Fix:** Remove the dead session assignment, or implement actual per-user isolation using this ID.

---

## 2. Duplicate Code

### 2.1 `_extract_and_store` and `_extract_and_store_kb` are Near-Identical
**Severity: Medium**  
**File:** `pharmagpt/app.py:271-296` and `pharmagpt/app.py:634-655`

Both functions contain the same extension-dispatch logic (`pdf` / `docx` / `xlsx` / `txt`), the same word-count calculation (`len(text.split())`), the same page-count estimate (`len(text.split()) // 300`), and the same silent error handler. The only difference is which DB write function they call at the end.

```python
# Duplicated identically in both functions:
elif extension == "txt":
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    pages = max(1, len(text.split()) // 300)
```

Any bug fix or improvement (e.g., adding logging as per §1.4) must be applied in two places.

**Fix:** Extract a shared helper and pass the DB save callable as a parameter:
```python
def _extract_text(file_path: str, extension: str) -> tuple[str, int]:
    """Returns (text, page_count). Raises on failure."""
    ...

def _extract_and_store(doc_id, project_id, file_path, extension):
    try:
        text, pages = _extract_text(file_path, extension)
        db.save_document_text(doc_id, project_id, text, pages, len(text.split()), "ok" if text.strip() else "empty")
    except Exception as exc:
        logging.error(...)
        db.save_document_text(doc_id, project_id, "", 0, 0, "error")
```

---

### 2.2 `safe_save` and `safe_save_kb` Duplicate Collision-Resolution Logic
**Severity: Low**  
**File:** `pharmagpt/documents.py:62-90` and `pharmagpt/documents.py:120-135`

Both functions implement the exact same filename collision-resolution loop:

```python
# Identical in safe_save (line 80-86) and safe_save_kb (line 126-131):
if os.path.exists(file_path):
    base, ext = os.path.splitext(safe_name)
    counter = 1
    while os.path.exists(file_path):
        safe_name = f"{base}_{counter}{ext}"
        file_path = os.path.join(upload_dir, safe_name)
        counter += 1
```

**Fix:** Extract a private helper:
```python
def _resolve_collision(upload_dir: str, safe_name: str) -> str:
    file_path = os.path.join(upload_dir, safe_name)
    if not os.path.exists(file_path):
        return safe_name
    base, ext = os.path.splitext(safe_name)
    counter = 1
    while os.path.exists(os.path.join(upload_dir, f"{base}_{counter}{ext}")):
        counter += 1
    return f"{base}_{counter}{ext}"
```

---

### 2.3 `doc_ids` Parameter Read But Ignored in Validation Generation
**Severity: Medium**  
**File:** `pharmagpt/app.py:394`, `pharmagpt/app.py:405-415`

The `/validation/generate` endpoint accepts a `doc_ids` list (line 394) which represents documents the user selected in wizard step 3 to use as reference:

```python
doc_ids = body.get("doc_ids", [])    # selected document IDs from Step 3
```

However, when building the document context (lines 405-415), `doc_ids` is only used as a truthy flag to decide *whether* to search — not to filter *which* documents to search. The actual search ignores `doc_ids` entirely and searches all documents in the project:

```python
if doc_ids:
    result = search_project_documents(
        query=f"{doc_type} validation ...",
        project_id=project_id,   # searches ALL project docs, not just doc_ids
        top_k=8,
        ...
    )
```

The user's document selection is silently discarded. This is a functional bug disguised as duplicate/dead logic.

**Fix:** Filter extracted texts by `doc_ids` before running the search, or pass `doc_ids` into `search_project_documents` as a filter parameter.

---

## 3. Dead Code / Unused Stubs

### 3.1 `extract_text()` in `documents.py` — Stale v0.5 Stub
**Severity: Medium**  
**File:** `pharmagpt/documents.py:159-169`

```python
def extract_text(file_path: str, extension: str) -> str:
    raise NotImplementedError(
        "Document text extraction will be implemented in v0.5. ..."
    )
```

Text extraction was implemented in v0.5, but it was implemented in `app.py` (`_extract_and_store`) and `services/pdf_reader.py` etc., not here. This function was never wired up and raises `NotImplementedError` if called. It is never called anywhere in the codebase.

**Fix:** Delete lines 159–169.

---

### 3.2 `analyze_with_gemini()` in `documents.py` — Stale v0.5 Stub
**Severity: Low**  
**File:** `pharmagpt/documents.py:172-179`

```python
def analyze_with_gemini(text: str, user_prompt: str, gemini_client) -> str:
    raise NotImplementedError("AI document analysis will be implemented in v0.5.")
```

Never called. The v0.5 feature it was intended for was implemented differently (RAG injection into the chat stream rather than a dedicated analysis route).

**Fix:** Delete lines 172–179.

---

### 3.3 `generate_embedding()` — Stale v0.6 Stub
**Severity: Low**  
**File:** `pharmagpt/services/document_search.py:182-187`

```python
def generate_embedding(text: str, gemini_client) -> list[float]:
    raise NotImplementedError("Vector embeddings will be implemented in v0.6")
```

Never called. Raises immediately if called.

**Fix:** Delete lines 182–187. When vector RAG is actually implemented in v0.8, add this then.

---

### 3.4 `upsert_to_vector_store()` — Stale v0.6 Stub
**Severity: Low**  
**File:** `pharmagpt/services/document_search.py:190-195`

```python
def upsert_to_vector_store(doc_id: int, chunks: list[str], vectors: list[list[float]]):
    raise NotImplementedError("Vector store upsert will be implemented in v0.6")
```

Never called.

**Fix:** Delete lines 190–195.

---

### 3.5 `vector_search()` — Stale v0.6 Stub
**Severity: Low**  
**File:** `pharmagpt/services/document_search.py:198-203`

```python
def vector_search(query_vector: list[float], project_id: int, top_k: int = 5):
    raise NotImplementedError("Vector search will be implemented in v0.6")
```

Never called.

**Fix:** Delete lines 198–203.

---

### 3.6 `get_document_text()` in `database.py` — Defined, Never Called
**Severity: Low**  
**File:** `pharmagpt/database.py:332-339`

```python
def get_document_text(document_id: int) -> dict | None:
    """Return the document_text row for a document, or None if not extracted."""
```

This function is defined but never called from `app.py` or any service. The codebase always uses `get_all_document_texts(project_id)` (the bulk loader) rather than fetching a single document's text. Likely written in anticipation of a per-document preview feature that was not implemented.

**Fix:** Delete or keep with a `# reserved for v0.8 document preview` comment.

---

### 3.7 `import math` Used Only for a Marginal Scoring Bonus
**Severity: Info**  
**File:** `pharmagpt/services/document_search.py:22`, `document_search.py:86`

```python
import math
...
length_bonus = math.log(max(len(chunk.split()), 1)) / 100
```

The `math` import is used, but the only usage is this tiny length bonus which adds at most ~0.055 to a score (log(400)/100). Given that it divides by 100, the length bonus is almost negligible and rarely changes chunk ranking. Not truly dead code, but worth noting as over-engineering.

---

## 4. Unused API Routes

### 4.1 `PUT /val-projects/<id>` — No Frontend Caller
**Severity: Low**  
**File:** `pharmagpt/app.py:760-768`

```python
@app.route("/val-projects/<int:vp_id>", methods=["PUT"])
def vp_update(vp_id):
    """Update a validation project's fields."""
```

A search of `val_workspace.js` reveals no `fetch` call to `PUT /val-projects/...`. There is no edit form wired up in the validation workspace UI. The route exists and is functional on the backend, but the frontend has no way to reach it.

**Fix:** Either build the edit UI in v0.8 (planned), or note it as a stub route.

---

### 4.2 `POST /val-projects/<id>/audit-trail` — No Frontend Caller
**Severity: Low**  
**File:** `pharmagpt/app.py:788-802`

```python
@app.route("/val-projects/<int:vp_id>/audit-trail", methods=["POST"])
def vp_add_audit(vp_id):
    """Append a manual audit entry."""
```

`val_workspace.js` only reads audit entries (`GET /val-projects/<id>/audit-trail` in `loadAuditTrail()`). There is no "Add Note" form or button that calls the POST endpoint. Manual audit entries cannot be created from the UI.

**Fix:** Add a "Add Note" input field to the Audit Trail tab, or document this as a planned v0.8 feature.

---

## 5. Performance Issues

### 5.1 Full Text Corpus Loaded into RAM on Every Search Query
**Severity: High**  
**File:** `pharmagpt/services/document_search.py:117`, `pharmagpt/database.py:342-362`

Every chat message that uses documents triggers `db.get_all_document_texts(project_id)`, which fetches the full `text_content` of every document in the project. For a project with 20 documents averaging 50,000 words each, this is 1 MB of text pulled from SQLite, loaded into Python, chunked, and scored — on every single message.

```python
# document_search.py:117
rows = db.get_all_document_texts(project_id)
```

There is no caching of chunks between queries, no pre-computed index, and no incremental update when new documents are uploaded.

**Fix (short-term):** Cache chunked document text in memory per project, invalidated on document upload/delete. **Fix (long-term):** Implement vector embeddings (v0.8) so searches are O(1) lookup rather than O(documents × words).

---

### 5.2 No Database Indexes on Frequently Queried Columns
**Severity: High**  
**File:** `pharmagpt/database.py:43-183` (`init_db`)

The schema creates no explicit indexes beyond the primary keys and the `UNIQUE` constraint on `document_text.document_id`. The following columns are filtered or sorted on in hot paths but have no index:

| Table | Column | Query |
|-------|--------|-------|
| `messages` | `project_id` | Every history load |
| `documents` | `project_id` | Every document list |
| `document_text` | `project_id` | Every RAG search |
| `kb_documents` | `folder` | Folder filter |
| `kb_documents` | `file_type` | File type filter |
| `generated_documents` | `project_id` | Generated doc list |
| `val_audit_trail` | `val_proj_id` | Audit trail load |

With small data volumes this is invisible. With thousands of messages or hundreds of KB documents, full-table scans become a bottleneck.

**Fix:** Add to `init_db()`:
```sql
CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_document_text_project ON document_text(project_id);
CREATE INDEX IF NOT EXISTS idx_kb_folder ON kb_documents(folder);
CREATE INDEX IF NOT EXISTS idx_kb_file_type ON kb_documents(file_type);
CREATE INDEX IF NOT EXISTS idx_generated_docs_project ON generated_documents(project_id);
CREATE INDEX IF NOT EXISTS idx_audit_val_proj ON val_audit_trail(val_proj_id);
```

---

### 5.3 Unbounded In-Memory History Cache
**Severity: Medium**  
**File:** `pharmagpt/app.py:31`

```python
history_cache: dict[int, list] = {}
```

The cache maps `project_id → list[Content]` with no size cap and no eviction policy. Each `Content` object holds the full text of every message ever sent in a project. A project with 500 messages averaging 500 words each consumes ~2.5 MB of RAM per project, and every project ever opened in a server session accumulates in this dict indefinitely.

**Fix:** Limit the history fed to Gemini to the last N turns (e.g., last 30), both in the cache and when loading from DB. Gemini does not benefit from thousands of old messages and the API has token limits anyway.

---

### 5.4 Full Reply Accumulated in Memory During Streaming
**Severity: Low**  
**File:** `pharmagpt/app.py:169`, `pharmagpt/app.py:432`

```python
full_reply = ""
for chunk in ...:
    full_reply += chunk.text
    yield ...
```

String concatenation inside a loop (`+=`) in Python creates a new string object on each iteration. For a 5,000-token response this is negligible, but for very long validation documents (10,000+ tokens), this creates many intermediate string objects. Python's string interning mitigates this somewhat, but a `list` + `join` pattern is more efficient.

**Fix:**
```python
chunks = []
for chunk in ...:
    chunks.append(chunk.text)
    yield ...
full_reply = "".join(chunks)
```

---

### 5.5 Synchronous Text Extraction Blocks the Upload Request
**Severity: Medium**  
**File:** `pharmagpt/app.py:265-266`

```python
_extract_and_store(doc_id, project_id,
                   docs.get_file_path(project_id, stored_filename), extension)
return jsonify(doc), 201
```

Text extraction runs synchronously inside the upload request handler. For a 200-page PDF, `pdfplumber` may take 10–20 seconds. During this time the HTTP connection is held open, the browser shows a spinner, and Flask's development server is blocked from handling other requests.

**Fix (v0.8):** Move extraction to a background thread (`threading.Thread`) or use Flask's `after_this_request` pattern. Return `201` immediately with `extraction_status: 'pending'`, and poll for completion via the insights endpoint.

---

## 6. UI Inconsistencies

### 6.1 Error Display Is Inconsistent Across Modules
**Severity: Medium**

Different JavaScript modules use different error presentation patterns with no shared utility:

| File | Error Handling Style |
|------|---------------------|
| `chat.js:237` | Appends styled `.error-bubble` element to chat |
| `projects.js` | `console.error()` only — no user-visible feedback |
| `val_workspace.js:36` | `console.error()` only — no user-visible feedback |
| `knowledge_base.js` | Inline `<div class="kb-error">` inside the list panel |
| `documents.js` | Alert via `console.error()` |

A user who encounters a network failure in the KB or Workspace views gets no indication that anything went wrong.

**Fix:** Create a shared `showToast(message, type)` function (referenced in all modules) that displays a consistent notification overlay.

---

### 6.2 `firstChunkReceived` Flag Scope Is Fragile
**Severity: Low**  
**File:** `pharmagpt/static/js/chat.js:174`

```javascript
let firstChunkReceived = false;
...
if (!firstChunkReceived) {
    thinkingEl.style.display = "none";
    bubble.classList.add("has-content");
    firstChunkReceived = true;
}
```

The flag is correctly scoped inside `sendMessage()` (so it resets each call), but the name suggests it tracks a global state. If `sendMessage` is ever refactored to be called recursively or in an async chain, the closure-per-call pattern will be non-obvious.

**Fix:** Rename to `isThinkingVisible` and use a guard that directly checks the element's display state instead of a boolean flag:
```javascript
if (thinkingEl.style.display !== "none") {
    thinkingEl.style.display = "none";
    bubble.classList.add("has-content");
}
```

---

### 6.3 Validation Workspace Uses a Different `esc()` Helper Than the Rest of the App
**Severity: Low**  
**File:** `pharmagpt/static/js/val_workspace.js:377-382`

`val_workspace.js` defines its own private `esc()` function inside its IIFE:
```javascript
function esc(str) {
    return String(str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
```

Other modules (`knowledge_base.js`) also define an equivalent local `escHtml()`. This is not wrong, but it means HTML-escaping logic is duplicated three or more times. If a bug is found (e.g., missing `'` → `&#039;` for single-quote contexts), it must be fixed in each copy independently.

**Fix:** Expose a single `window.escHtml()` utility from a shared helper script loaded before all modules.

---

### 6.4 The Workspace `showView()` Shadows the Global View Switcher
**Severity: Medium**  
**File:** `pharmagpt/static/js/val_workspace.js:360-372`

`val_workspace.js` defines a local `showView()` function inside its IIFE. The global view-switching logic in `index.html` also has a `showView()` or equivalent. The local one operates on `<main id^='view-'>` elements but also manipulates sidebar `.active` states:

```javascript
function showView(viewId) {
    document.querySelectorAll("main[id^='view-']").forEach(v => v.style.display = "none");
    const target = $(viewId);
    if (target) target.style.display = "flex";
    // manually resets nav active states
    document.querySelectorAll(".sidebar-item[data-view]").forEach(...);
    document.querySelectorAll(".val-nav-item").forEach(...);
}
```

This creates two separate competing implementations of view switching with different assumptions about which elements they manage. If the sidebar structure changes, both must be updated in sync.

**Fix:** Use the global view-switcher and pass view-specific navigation state as a parameter, rather than re-implementing it locally.

---

### 6.5 `populateOverview` Renders "Target Date" Twice
**Severity: Low**  
**File:** `pharmagpt/static/js/val_workspace.js:260`, `val_workspace.js:285`

In the overview panel, "Target Date" appears in both the "Project Information" card and the "Timeline" card:

```javascript
// Project Information card (line 260):
${kv("Target Date", p.target_date ? fmtDate(p.target_date) : "")}

// Timeline card (line 285):
${kv("Target Date", p.target_date ? fmtDate(p.target_date) : "")}
```

This is redundant and potentially confusing if the two values ever diverge (e.g., if one is formatted differently).

**Fix:** Remove "Target Date" from the Timeline card and replace it with a more useful field, such as "Days Remaining" (calculated from today) or "Last Updated".

---

## 7. Unused CSS

### 7.1 `.has-content` Class Added in JS but Styled Nowhere
**Severity: Low**  
**File:** `pharmagpt/static/js/chat.js:217`, `pharmagpt/static/css/style.css`

```javascript
bubble.classList.add("has-content");
```

`has-content` is added to the streaming bubble when the first token arrives, but a search of `style.css` reveals no rule targeting `.bubble.has-content` or `.has-content`. The class is applied but produces no visual effect.

**Fix:** Either add a CSS rule (e.g., remove a minimum-height placeholder), or remove the `classList.add` call.

---

### 7.2 `.streaming` Class Applied but Not Visually Differentiated From Final State
**Severity: Info**  
**File:** `pharmagpt/static/js/chat.js:89`, `pharmagpt/static/js/chat.js:226`

```javascript
bubble.className = "bubble streaming";  // on creation
...
bubble.classList.remove("streaming");   // on done
```

If `style.css` does not define a distinct style for `.bubble.streaming` vs `.bubble`, the user cannot tell that a response is still streaming vs complete. The thinking dots indicate this during the preamble, but once content begins flowing, the streaming state is invisible.

**Fix:** Add a CSS rule such as a subtle animated underline or border pulse for `.bubble.streaming` to indicate in-progress generation.

---

## 8. Unused JavaScript

### 8.1 `removeStreamingRow()` Is Defined but Only Called on Error
**Severity: Info**  
**File:** `pharmagpt/static/js/chat.js:122-125`

```javascript
function removeStreamingRow() {
    const el = document.getElementById("streaming-row");
    if (el) el.remove();
}
```

This function is only called in two error-path branches (line 209, line 235). In the normal success path, the streaming row is kept in place (it becomes the completed message). This is correct behaviour, but the function name is slightly misleading — it does not clean up the row at the end of streaming, only on failure. No true dead code issue, but worth noting for readability.

---

### 8.2 `_activeProj` Stored in `val_workspace.js` But Only Partially Used
**Severity: Low**  
**File:** `pharmagpt/static/js/val_workspace.js:15`, `val_workspace.js:345`

```javascript
let _activeProj = null;
...
if (tabName === "audit" && _activeProj) {
    loadAuditTrail(_activeProj.id);
}
```

`_activeProj` is set in `openWorkspace()` and used only to reload the audit trail on tab switch. The full project object is stored but all its individual fields are read directly from the `proj` local variable in `populateOverview()` and `populateEquipment()` — `_activeProj` is not used for those. The update button (not yet wired) would need `_activeProj`, but as noted in §4.1, that route has no frontend caller yet.

**Fix:** Either use `_activeProj` consistently for all workspace rendering, or reduce it to `_activeProjId` (an integer) since the full object is fetched fresh via `fetchProject()` anyway.

---

## 9. Additional Observations

### 9.1 No Logging Framework
**Severity: Medium**  
**File:** `pharmagpt/app.py` (entire file)

There are no `import logging` statements in `app.py`, `database.py`, or any service. Errors are either swallowed silently (§1.4) or printed via Flask's default WSGI logger only if they are uncaught exceptions. In production, diagnosing extraction failures, slow queries, or Gemini API errors is impossible without structured logs.

**Recommendation:** Add Python's standard `logging` module at the top of `app.py` and each service. Log at `INFO` for key operations (project created, file uploaded, generation started) and `ERROR` for all caught exceptions.

---

### 9.2 No Unit Tests
**Severity: Medium**  

No test files exist in the repository (no `test_*.py`, no `tests/` directory, no `*.test.js`). The most critical and self-contained logic — the RAG scoring algorithm in `document_search.py`, the DOCX state machine in `doc_exporter.py`, and all database CRUD functions — has zero test coverage.

**Recommendation:** Add `pytest` with at least:
- `test_document_search.py` — verify chunk scoring, boundary cases (empty text, single word queries)
- `test_database.py` — verify cascade deletes, FK enforcement, `get_project_insights` aggregation
- `test_doc_exporter.py` — verify headings, tables, and bold/italic render correctly to DOCX

---

### 9.3 `import` Inside a Function Body
**Severity: Low**  
**File:** `pharmagpt/app.py:407`

```python
from services.document_search import search_project_documents
```

This import is inside the `validation_generate()` route handler. It is already imported at the top of the file on line 11. The second import is redundant and slightly wasteful (Python caches modules, so it's not a real performance issue, but it is inconsistent style).

**Fix:** Remove the duplicate import at line 407.

---

### 9.4 `BytesIO` Import Inside Function Body
**Severity: Low**  
**File:** `pharmagpt/app.py:480`

```python
from io import BytesIO
```

This import is inside `validation_export_docx()`. `BytesIO` should be imported at the top of `app.py` with the other imports.

**Fix:** Move to the top-level imports.

---

### 9.5 Magic Number `300` for Words-Per-Page Estimate Used Twice
**Severity: Low**  
**File:** `pharmagpt/app.py:287`, `pharmagpt/app.py:646`

```python
pages = max(1, len(text.split()) // 300)
```

The constant `300` (words per page) appears identically in both `_extract_and_store` and `_extract_and_store_kb`. It should be a named constant in `config.py`:

```python
WORDS_PER_PAGE_ESTIMATE = 300
```

---

### 9.6 Dashboard Stats Use Multiple Subqueries in One SQL Call
**Severity: Info**  
**File:** `pharmagpt/database.py:704-741`

`get_dashboard_stats()` is well-structured and efficiently batches 6 queries into one connection context. However, the `recent_activity` query uses `UNION ALL` across four tables and then orders the entire union by `created_at` without a limit on each sub-select. With large tables, this materialises all four result sets before applying the `LIMIT 10`. This is a minor inefficiency that will only matter at scale.

**Fix:** At large scale, replace with separate queries or add `LIMIT N` to each sub-select before the `UNION ALL`.

---

## 10. Recommended Priority Order

### Immediate (before any public exposure)
1. **§1.1** — Add DOMPurify to sanitize all `marked.parse()` output
2. **§1.2** — Require `FLASK_SECRET_KEY` in environment, fail without it
3. **§1.3** — Add CSRF protection to all state-modifying routes
4. **§1.4** — Add logging to both `_extract_and_store` functions

### Short-term (next sprint)
5. **§1.5** — Add rate limiting on `/stream` and `/validation/generate`
6. **§5.2** — Add database indexes for all FK and filter columns
7. **§2.3** — Fix the `doc_ids` parameter being ignored in validation generation
8. **§9.1** — Set up structured logging throughout the application

### Medium-term (v0.8)
9. **§5.1** — Cache chunked documents per project, or move to vector RAG
10. **§5.5** — Make file extraction async (background thread)
11. **§3.1–3.5** — Remove all five `NotImplementedError` stub functions
12. **§2.1** — Consolidate the two text-extraction functions

### Low priority (backlog)
13. **§4.1–4.2** — Wire up unused backend routes or document as stubs
14. **§6.1** — Build a shared toast/notification system
15. **§9.2** — Add pytest coverage for RAG, DB, and DOCX export
16. **§9.3–9.4** — Move inline imports to the top of `app.py`
