# Product Requirements Document — PharmaGPT

**Version:** 1.0  
**Date:** 2026-06-27  
**Status:** Active  
**Current Release:** v0.7 (Knowledge Base)

---

## 1. Executive Summary

PharmaGPT is a web-based pharmaceutical operations and validation AI consultant. It provides pharmaceutical manufacturing teams with an intelligent assistant capable of answering compliance questions, generating regulatory-grade validation documents, and managing a structured knowledge base of SOPs, protocols, and reports — all grounded in the user's own uploaded documents.

The product targets quality assurance teams, validation engineers, and regulatory affairs professionals who need rapid, accurate guidance aligned with global pharmaceutical regulatory frameworks (USFDA, EU GMP, MHRA, WHO-GMP, CDSCO, TGA).

---

## 2. Goals & Objectives

| Goal | Metric |
|------|--------|
| Reduce time to produce first-draft validation documents | From ~4 hours to < 10 minutes |
| Surface relevant SOPs/protocols during consultation | AI cites source documents in every RAG-assisted response |
| Maintain regulatory accuracy | Responses grounded in 21 CFR, EU GMP Annex, ICH Q guidelines |
| Enable a centralised, searchable document library | Knowledge Base supports keyword, folder, tag, and file-type search |
| Provide an audit-ready document generation trail | All generated docs saved with metadata; DOCX export with headers/footers |

---

## 3. Users & Personas

### 3.1 Primary: Validation Engineer
- Runs IQ/OQ/PQ protocols for new equipment
- Needs to produce URS, DQ, FAT, SAT documents quickly
- Uploads vendor manuals and internal SOPs for context
- Values: speed, structural accuracy, reference to regulatory standards

### 3.2 Secondary: QA/QC Manager
- Reviews deviation reports, CAPAs, change controls
- Uses the AI to sanity-check logic and suggest corrective actions
- Manages the Knowledge Base folder structure for the team
- Values: document traceability, version control, audit readiness

### 3.3 Tertiary: Regulatory Affairs Specialist
- Prepares submissions for CDSCO, USFDA, EU GMP inspections
- Queries the AI on specific regulatory clauses and applicability
- Values: citation accuracy, ability to attach regulatory PDFs to context

---

## 4. Functional Requirements

### 4.1 AI Consultation (Chat)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-C01 | System must stream AI responses token-by-token via SSE | Must Have |
| FR-C02 | AI persona must reflect 30+ years pharmaceutical expertise | Must Have |
| FR-C03 | System must support per-project conversation history persisted to DB | Must Have |
| FR-C04 | User must be able to inject uploaded project documents into AI context | Must Have |
| FR-C05 | AI response must display which source documents were used (sources strip) | Must Have |
| FR-C06 | User must be able to clear conversation history per project | Must Have |
| FR-C07 | System must handle Gemini API errors gracefully with user-facing messages | Must Have |
| FR-C08 | AI must cite applicable regulatory frameworks by name (21 CFR, EU GMP, etc.) | Should Have |

### 4.2 Project Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-P01 | User can create a project with equipment name, manufacturer, department, validation type | Must Have |
| FR-P02 | Projects are listed in the sidebar with creation timestamp | Must Have |
| FR-P03 | Deleting a project cascades to messages, documents, and generated docs | Must Have |
| FR-P04 | Active project context is maintained across all views (chat, docs, validation) | Must Have |

### 4.3 Document Upload & Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-D01 | System must accept PDF, DOCX, XLSX, TXT (max 50 MB per file) | Must Have |
| FR-D02 | Documents must be stored per-project in isolated directories | Must Have |
| FR-D03 | Text must be auto-extracted from all supported file types on upload | Must Have |
| FR-D04 | User can view PDF/TXT inline in the browser | Must Have |
| FR-D05 | User can force-download any uploaded document | Must Have |
| FR-D06 | User can delete a document (removes DB record + physical file) | Must Have |
| FR-D07 | Drag-and-drop upload must be supported | Should Have |
| FR-D08 | Document Insights panel must display count, total pages, words, extraction status | Should Have |

### 4.4 Validation Document Generator

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-V01 | System must support 11 document types: URS, DQ, FAT, SAT, IQ, OQ, PQ, FMEA, CAPA, Deviation, Change Control | Must Have |
| FR-V02 | Generation UI must be a 4-step wizard (equipment → fields → references → generation) | Must Have |
| FR-V03 | Generation must stream in real-time into an A4-style document viewer | Must Have |
| FR-V04 | User can export generated document to styled DOCX | Must Have |
| FR-V05 | User can export generated document to PDF via browser print | Must Have |
| FR-V06 | User can save generated document to project for later retrieval | Must Have |
| FR-V07 | Saved documents must be re-openable and deletable | Must Have |
| FR-V08 | Generation temperature must be set to 0.3 for structural consistency | Must Have |
| FR-V09 | User can select uploaded project documents as reference material for generation | Should Have |
| FR-V10 | Each doc type must have distinct colour and icon in the wizard UI | Nice to Have |

### 4.5 Knowledge Base

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-K01 | Knowledge Base must be project-independent (global library) | Must Have |
| FR-K02 | System must support 8 folders: SOP, Validation, Qualification, Protocols, Reports, Regulations, Vendor Documents, Others | Must Have |
| FR-K03 | Each document must support metadata: Title, Folder, Tags, Version, Effective Date, Review Date | Must Have |
| FR-K04 | User can search KB by title keyword, tag, file type, and full-text keyword | Must Have |
| FR-K05 | Sidebar must display live document counts per folder | Must Have |
| FR-K06 | Clicking a KB document opens a detail panel with full metadata and text preview | Must Have |
| FR-K07 | Overdue review dates must be visually highlighted | Should Have |
| FR-K08 | User can view PDF/TXT inline or force-download any KB file | Must Have |
| FR-K09 | User can delete KB documents (removes DB record + physical file) | Must Have |

### 4.6 Dashboard

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-H01 | Home dashboard must display system-wide stats (projects, KB docs, validation projects, protocols generated) | Must Have |

---

## 5. Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | First AI token latency | < 3 seconds |
| NFR-02 | Document text extraction time | < 10 seconds for a 100-page PDF |
| NFR-03 | DOCX export time | < 5 seconds |
| NFR-04 | Maximum file upload size | 50 MB |
| NFR-05 | Application must run on Windows 10 without external services | SQLite, no PostgreSQL/Redis required |
| NFR-06 | UI must render correctly in Chrome (primary), Firefox, Edge | Cross-browser |
| NFR-07 | All file uploads must use `secure_filename` to prevent path traversal | Security |
| NFR-08 | `.env` and `.db` files must be excluded from version control | Security |
| NFR-09 | API keys must never be exposed to the client | Security |

---

## 6. Out of Scope (Current Version)

- Multi-user authentication / RBAC (planned v0.9)
- Vector embedding RAG (planned v0.8)
- Electronic signature workflows (planned v0.8)
- Email notifications
- Cloud deployment / multi-tenancy
- Mobile-native app

---

## 7. Acceptance Criteria (v0.7)

- [x] Chat streams correctly and cites source documents
- [x] Projects create, list, and delete with full cascade
- [x] PDF, DOCX, XLSX, TXT upload and text extraction works
- [x] All 11 validation document types generate and export to DOCX
- [x] Knowledge Base accepts files with metadata and supports all search modes
- [x] Folder counts update live in KB sidebar
- [x] Dashboard stats load on home view

---

## 8. Dependencies

| Dependency | Purpose | Version |
|------------|---------|---------|
| Google Gemini API | LLM inference & streaming | gemini-2.5-flash |
| Flask | Web framework | latest |
| pdfplumber | PDF text extraction | latest |
| python-docx | DOCX read/write | latest |
| openpyxl | XLSX extraction | latest |
| marked.js | Client-side markdown rendering | CDN |
| SQLite 3 | Persistent storage | bundled with Python |
