# PharmaGPT — API Reference

**Base URL:** `http://127.0.0.1:5000` (configurable via `FLASK_PORT` in `.env`)  
**Format:** All request and response bodies are JSON unless noted otherwise.  
**Auth:** None in v0.6 (planned for v0.9).

---

## Core

### `GET /`
Serves the single-page application shell (`index.html`).

---

## Projects

### `GET /projects`
List all projects, newest first.

**Response `200`**
```json
[
  {
    "id": 1,
    "name": "HPLC Qualification 2026",
    "equipment_name": "Agilent HPLC 1260",
    "manufacturer": "Agilent Technologies",
    "department": "Quality Control",
    "validation_type": "IQ/OQ/PQ",
    "created_at": "2026-06-27T10:30:00"
  }
]
```

---

### `POST /projects`
Create a new project.

**Request body**
```json
{
  "name": "HPLC Qualification 2026",
  "equipment_name": "Agilent HPLC 1260",
  "manufacturer": "Agilent Technologies",
  "department": "Quality Control",
  "validation_type": "IQ/OQ/PQ"
}
```
Only `name` is required.

**Response `201`**
```json
{ "id": 1, "message": "Project created" }
```

---

### `GET /projects/<id>`
Get a single project by ID.

**Response `200`** — same shape as one item from `GET /projects`.  
**Response `404`** — `{ "error": "Project not found" }`

---

### `DELETE /projects/<id>`
Delete a project and all its messages, documents, and generated docs (cascade).

**Response `200`** — `{ "message": "Project deleted" }`  
**Response `404`** — `{ "error": "Project not found" }`

---

### `GET /projects/<id>/messages`
Load the full chat history for a project.

**Response `200`**
```json
[
  { "role": "user",  "content": "What is IQ validation?" },
  { "role": "model", "content": "Installation Qualification (IQ) is..." }
]
```

---

### `POST /stream`
Send a chat message and receive an SSE stream of Gemini tokens.

**Request body**
```json
{
  "project_id": 1,
  "message": "Summarise the URS",
  "use_documents": true
}
```

**Response** — `text/event-stream`

| Event data | Meaning |
|------------|---------|
| `data: <token text>` | Streamed text token |
| `data: [DONE]` | Stream complete, no sources |
| `data: [DONE:source1.pdf,source2.docx]` | Stream complete with sources |
| `data: [ERROR] <message>` | Gemini or server error |

---

### `POST /clear`
Clear the chat history for a project (in-memory cache + DB).

**Request body**
```json
{ "project_id": 1 }
```

**Response `200`** — `{ "message": "History cleared" }`

---

## Documents

### `GET /projects/<id>/documents`
List all uploaded documents for a project.

**Response `200`**
```json
[
  {
    "id": 3,
    "project_id": 1,
    "original_name": "Equipment Manual.pdf",
    "stored_filename": "Equipment_Manual.pdf",
    "file_type": "pdf",
    "file_size": 2048576,
    "upload_date": "2026-06-27T11:00:00"
  }
]
```

---

### `POST /projects/<id>/documents`
Upload a file. Auto-extracts text after saving.

**Request** — `multipart/form-data`

| Field | Type | Notes |
|-------|------|-------|
| `file` | binary | PDF, DOCX, XLSX, or TXT; max 50 MB |

**Response `201`**
```json
{
  "id": 3,
  "original_name": "Equipment Manual.pdf",
  "file_type": "pdf",
  "file_size": 2048576,
  "extraction_status": "ok"
}
```

**Response `400`** — file type not allowed or no file provided.

---

### `GET /documents/<id>/view`
View the file inline (PDF/TXT) or trigger browser download (DOCX/XLSX).

**Response** — raw file bytes with appropriate `Content-Type`.

---

### `GET /documents/<id>/download`
Force-download the file regardless of type.

**Response** — raw file bytes with `Content-Disposition: attachment`.

---

### `DELETE /documents/<id>`
Delete document metadata from DB and remove the file from disk.

**Response `200`** — `{ "message": "Document deleted" }`  
**Response `404`** — `{ "error": "Document not found" }`

---

### `GET /projects/<id>/insights`
Aggregated document statistics for the Document Insights panel.

**Response `200`**
```json
{
  "total_documents": 4,
  "total_pages": 312,
  "total_words": 87430,
  "extraction_ok": 3,
  "extraction_empty": 0,
  "extraction_error": 1,
  "by_type": {
    "pdf": 2,
    "docx": 1,
    "xlsx": 1
  }
}
```

---

## Validation — Document Generation

### `POST /validation/generate`
Generate a validation document and stream the Markdown content via SSE.

**Request body**
```json
{
  "project_id": 1,
  "doc_type": "OQ",
  "form_data": {
    "equipment_name": "Agilent HPLC 1260",
    "manufacturer": "Agilent Technologies",
    "department": "Quality Control",
    "validation_type": "OQ",
    "software_version": "OpenLAB CDS 2.7",
    "installation_site": "QC Lab, Building 3"
  },
  "reference_doc_ids": [3, 5]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `project_id` | Yes | |
| `doc_type` | Yes | One of: `URS`, `DQ`, `FAT`, `SAT`, `IQ`, `OQ`, `PQ`, `FMEA`, `CAPA`, `Deviation`, `ChangeControl` |
| `form_data` | Yes | Key-value pairs from wizard step 2 |
| `reference_doc_ids` | No | Array of document IDs to inject as context |

**Response** — `text/event-stream`

| Event | Meaning |
|-------|---------|
| `data: <markdown token>` | Streamed Markdown text |
| `data: [DONE]` | Generation complete |
| `data: [ERROR] <message>` | Generation failed |

---

### `POST /validation/export/docx`
Convert Markdown content to a styled DOCX file and return it as a download.

**Request body**
```json
{
  "content": "# Operational Qualification Protocol\n\n## 1. Purpose\n...",
  "title": "Agilent HPLC 1260 — OQ Protocol"
}
```

**Response** — `application/vnd.openxmlformats-officedocument.wordprocessingml.document`  
Binary DOCX file with `Content-Disposition: attachment; filename="<title>.docx"`.

---

### `POST /validation/save`
Save a generated document to the database.

**Request body**
```json
{
  "project_id": 1,
  "doc_type": "OQ",
  "title": "Agilent HPLC 1260 — OQ Protocol",
  "form_data": { "equipment_name": "Agilent HPLC 1260", "..." : "..." },
  "content": "# Operational Qualification Protocol\n\n..."
}
```

**Response `201`**
```json
{ "id": 7, "message": "Document saved" }
```

---

### `GET /projects/<id>/generated-docs`
List all saved generated documents for a project.

**Response `200`**
```json
[
  {
    "id": 7,
    "project_id": 1,
    "doc_type": "OQ",
    "title": "Agilent HPLC 1260 — OQ Protocol",
    "created_at": "2026-06-27T14:22:00"
  }
]
```
Note: `content` and `form_data` are excluded from the list view for performance.

---

### `GET /generated-docs/<id>`
Retrieve a single generated document including its full Markdown content.

**Response `200`**
```json
{
  "id": 7,
  "project_id": 1,
  "doc_type": "OQ",
  "title": "Agilent HPLC 1260 — OQ Protocol",
  "form_data": { "equipment_name": "Agilent HPLC 1260" },
  "content": "# Operational Qualification Protocol\n\n...",
  "created_at": "2026-06-27T14:22:00"
}
```

**Response `404`** — `{ "error": "Document not found" }`

---

### `DELETE /generated-docs/<id>`
Delete a saved generated document.

**Response `200`** — `{ "message": "Document deleted" }`  
**Response `404`** — `{ "error": "Document not found" }`

---

## Error Responses

All errors follow this shape:

```json
{ "error": "Human-readable description" }
```

| HTTP Status | Meaning |
|-------------|---------|
| `400` | Bad request — missing required field or invalid input |
| `404` | Resource not found |
| `413` | File too large (> 50 MB) |
| `415` | File type not allowed |
| `500` | Internal server error |

---

## SSE Protocol Detail

Endpoints that stream (`/stream`, `/validation/generate`) use chunked transfer encoding:

```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

Each line is `data: <payload>\n\n`. The client reads with `ReadableStream` / `TextDecoder`. Terminal signals:

- `[DONE]` — success, no source documents used
- `[DONE:file1.pdf,file2.docx]` — success, these source files were used (chat only)
- `[ERROR] <message>` — failure; message is shown to the user

---

## Quality Management Suite (Phase 1) — added 2026-07-02

Full reference: [`docs/QMS_PHASE1.md`](docs/QMS_PHASE1.md). All bodies are JSON except file
upload (multipart/form-data) and DOCX export (binary download).

**Shared** (`routes/qms_common.py`) — `record_type` ∈ `document | deviation | capa | change_control`:
- `GET /qms/dashboard` — unified stats across all 3 modules
- `GET /qms/meta` — enum lists (doc types, statuses, categories) for dropdowns
- `GET|POST /qms/<record_type>/<id>/attachments`, `GET /qms/attachments/<id>/download`, `DELETE /qms/attachments/<id>`
- `GET|POST /qms/<record_type>/<id>/comments`
- `GET /qms/<record_type>/<id>/audit-trail`
- `GET /qms/<record_type>/<id>/approval` (POST is module-specific — see below, since each module maps the action to a different status transition)

**Document Control** (`routes/qms_documents.py`, prefix `/qms/documents`):
- `GET|POST /qms/documents`, `GET|PUT|DELETE /qms/documents/<id>`
- `POST /qms/documents/<id>/generate` — AI draft generation (SSE stream)
- `POST /qms/documents/<id>/review` — AI regulatory compliance review
- `GET|POST /qms/documents/<id>/versions`, `GET|POST /qms/documents/<id>/training`, `PUT /qms/documents/training/<id>`
- `GET|POST /qms/documents/<id>/distribution`, `POST /qms/documents/distribution/<id>/acknowledge`
- `POST /qms/documents/<id>/approval` — status transition + e-signature
- `GET /qms/documents/<id>/report`, `POST /qms/documents/<id>/export/docx`

**Deviation Management** (`routes/qms_deviations.py`, prefix `/qms/deviations`):
- `GET|POST /qms/deviations`, `GET|PUT|DELETE /qms/deviations/<id>`
- `POST /qms/deviations/<id>/investigate` — AI Investigation Assistant (fishbone/5-Why/timeline/root cause)
- `GET|PUT /qms/deviations/<id>/investigation`
- `POST /qms/deviations/<id>/suggest-impact`, `GET|POST /qms/deviations/<id>/impact`
- `POST /qms/deviations/<id>/suggest-capa`, `POST /qms/deviations/<id>/link-capa`, `GET /qms/deviations/<id>/capas`
- `POST /qms/deviations/<id>/approval`
- `GET /qms/deviations/<id>/report`, `POST /qms/deviations/<id>/export/docx`

**CAPA** (`routes/qms_capa.py`, prefix `/qms/capa`):
- `GET|POST /qms/capa`, `GET|PUT|DELETE /qms/capa/<id>`
- `POST /qms/capa/<id>/suggest-draft`, `POST /qms/capa/<id>/suggest-effectiveness`
- `GET /qms/capa/trend-summary` — AI Quality Trend Summary across CAPAs & Deviations
- `GET|POST /qms/capa/<id>/actions`, `POST /qms/capa/actions/<id>/escalate`
- `GET|POST /qms/capa/<id>/effectiveness`
- `GET /qms/capa/<id>/deviations` — linked deviations
- `POST /qms/capa/<id>/approval`
- `GET /qms/capa/<id>/report`, `POST /qms/capa/<id>/export/docx`

---

## Quality Management Suite (Phase 2: Change Control) — added 2026-07-05

Full reference: [`docs/QMS_PHASE2.md`](docs/QMS_PHASE2.md). Follows the exact Phase 1 pattern above
— shared endpoints now also serve `record_type='change_control'`.

**Change Control** (`routes/qms_change_control.py`, prefix `/qms/change-control`):
- `GET|POST /qms/change-control`, `GET|PUT|DELETE /qms/change-control/<id>`
- `POST /qms/change-control/<id>/suggest-impact`, `GET|POST /qms/change-control/<id>/impact`
- `POST /qms/change-control/<id>/suggest-implementation-plan`, `GET|POST /qms/change-control/<id>/actions`
- `POST /qms/change-control/<id>/risk-summary`, `.../rollback-plan`, `.../regulatory-impact`,
  `.../justification`, `.../executive-summary`, `.../verification-summary`,
  `.../effectiveness-review` — each returns `{"text": "..."}` and persists into `ai_narratives`
- `POST /qms/change-control/<id>/link-deviation`, `POST /qms/change-control/<id>/link-capa`
- `GET /qms/change-control/<id>/deviations`, `GET /qms/change-control/<id>/capas`
- `POST /qms/change-control/<id>/approval`
- `GET /qms/change-control/<id>/report`, `POST /qms/change-control/<id>/export/docx`
