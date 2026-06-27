// documents.js — manages the Documents view: upload, list, view, download, delete.
// Depends on window.activeProject (set by projects.js).

// ── DOM refs ──────────────────────────────────────────────────────────────────
const docListEl      = document.getElementById("doc-list");
const docEmptyEl     = document.getElementById("doc-empty");
const docUploadInput = document.getElementById("doc-file-input");
const docDropZone    = document.getElementById("doc-drop-zone");
const docUploadBtn   = document.getElementById("doc-upload-btn");
const docUploadStatus = document.getElementById("doc-upload-status");

// ── File type display config ──────────────────────────────────────────────────
const FILE_ICONS = { pdf: "📄", docx: "📝", xlsx: "📊", txt: "📃" };
const FILE_COLORS = {
  pdf:  "#E53935",   // red
  docx: "#1565C0",   // blue
  xlsx: "#2E7D32",   // green
  txt:  "#607080",   // grey
};

// ── Load and render document list ─────────────────────────────────────────────

async function loadDocuments() {
  if (!window.activeProject) return;

  try {
    const res = await fetch(`/projects/${window.activeProject.id}/documents`);
    const documents = await res.json();
    renderDocuments(documents);
  } catch {
    showDocStatus("Could not load documents.", "error");
  }
}

function renderDocuments(documents) {
  docListEl.innerHTML = "";

  if (!documents.length) {
    docEmptyEl.style.display = "flex";
    return;
  }

  docEmptyEl.style.display = "none";

  documents.forEach(doc => {
    const ext  = doc.file_type;
    const icon = FILE_ICONS[ext]  || "📎";
    const color = FILE_COLORS[ext] || "#607080";
    const size = formatSize(doc.file_size);
    const date = formatDate(doc.upload_date);

    // Can this file type be rendered in the browser?
    const canView = ext === "pdf" || ext === "txt";

    const row = document.createElement("div");
    row.className = "doc-row";
    row.innerHTML = `
      <div class="doc-icon" style="color:${color}">${icon}</div>
      <div class="doc-info">
        <div class="doc-name" title="${escapeHtml(doc.original_name)}">${escapeHtml(doc.original_name)}</div>
        <div class="doc-meta">
          <span class="doc-type-badge" style="border-color:${color};color:${color}">${ext.toUpperCase()}</span>
          <span>${size}</span>
          <span>${date}</span>
        </div>
      </div>
      <div class="doc-actions">
        ${canView
          ? `<a class="doc-btn doc-btn-view" href="/documents/${doc.id}/view" target="_blank">View</a>`
          : `<span class="doc-btn doc-btn-view doc-btn-disabled" title="This file type cannot be previewed in the browser">View</span>`
        }
        <a class="doc-btn doc-btn-download" href="/documents/${doc.id}/download" download>Download</a>
        <button class="doc-btn doc-btn-delete" data-id="${doc.id}" data-name="${escapeHtml(doc.original_name)}">Delete</button>
      </div>
    `;

    // Wire up the delete button
    row.querySelector(".doc-btn-delete").addEventListener("click", (e) => {
      const btn = e.currentTarget;
      confirmDeleteDocument(btn.dataset.id, btn.dataset.name);
    });

    docListEl.appendChild(row);
  });
}

// ── Upload ────────────────────────────────────────────────────────────────────

async function uploadFile(file) {
  if (!window.activeProject) {
    showDocStatus("Please select a project first.", "error");
    return;
  }

  const allowed = ["pdf", "docx", "xlsx", "txt"];
  const ext = file.name.split(".").pop().toLowerCase();
  if (!allowed.includes(ext)) {
    showDocStatus(`"${file.name}" is not an allowed type. Upload PDF, DOCX, XLSX, or TXT.`, "error");
    return;
  }

  showDocStatus(`Uploading "${file.name}"…`, "info");
  docUploadBtn.disabled = true;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(`/projects/${window.activeProject.id}/documents`, {
      method: "POST",
      body: formData,           // FormData sets Content-Type automatically (multipart)
    });

    const data = await res.json();

    if (!res.ok) {
      showDocStatus(data.error || "Upload failed.", "error");
    } else {
      showDocStatus(`"${data.original_name}" uploaded successfully.`, "success");
      await loadDocuments();
    }
  } catch {
    showDocStatus("Network error during upload. Please try again.", "error");
  } finally {
    docUploadBtn.disabled = false;
    docUploadInput.value = "";  // reset so the same file can be re-uploaded
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function confirmDeleteDocument(docId, docName) {
  if (!confirm(`Delete "${docName}"? This cannot be undone.`)) return;

  try {
    const res = await fetch(`/documents/${docId}`, { method: "DELETE" });
    if (!res.ok) throw new Error();
    showDocStatus(`"${docName}" deleted.`, "info");
    await loadDocuments();
  } catch {
    showDocStatus("Could not delete the file. Please try again.", "error");
  }
}

// ── Status banner ─────────────────────────────────────────────────────────────

let statusTimer = null;

function showDocStatus(message, type = "info") {
  // type: "info" | "success" | "error"
  docUploadStatus.textContent = message;
  docUploadStatus.className = `doc-status doc-status-${type}`;
  docUploadStatus.style.display = "block";

  // Auto-hide after 4 seconds
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => {
    docUploadStatus.style.display = "none";
  }, 4000);
}

// ── Drag and drop ─────────────────────────────────────────────────────────────

docDropZone.addEventListener("dragover", (e) => {
  e.preventDefault();   // required to allow drop
  docDropZone.classList.add("drag-over");
});

docDropZone.addEventListener("dragleave", () => {
  docDropZone.classList.remove("drag-over");
});

docDropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  docDropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});

// ── File input button ─────────────────────────────────────────────────────────

// "Choose File" button inside the drop zone triggers the hidden file input
docUploadBtn.addEventListener("click", () => docUploadInput.click());

docUploadInput.addEventListener("change", () => {
  if (docUploadInput.files[0]) uploadFile(docUploadInput.files[0]);
});

// ── Utilities ─────────────────────────────────────────────────────────────────

function formatSize(bytes) {
  if (bytes < 1024)        return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(isoString) {
  const d = new Date(isoString);
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── Expose loadDocuments so projects.js can call it on project switch ─────────
window.loadDocuments = loadDocuments;
