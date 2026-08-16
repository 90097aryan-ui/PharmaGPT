/*
 * qms_feature_requests.js — Feature Requests module frontend (v1: CRUD only).
 *
 * Renders entirely into <main id="view-feature-requests"><div id="feature-requests-body">.
 * Follows the same structure as qms_capa.js / qms_documents.js.
 */

function initFeatureRequests() {
  qmsLoadMeta().then(() => frShowList());
}
window.initFeatureRequests = initFeatureRequests;

// ── List view ───────────────────────────────────────────────────────────────

async function frShowList(filters = {}) {
  const body = document.getElementById("feature-requests-body");
  body.innerHTML = `
    <div class="qms-page-header">
      <div>
        <h2>Feature Requests</h2>
        <p>Track and triage feature ideas across Yuktav modules</p>
      </div>
      <div class="qms-header-actions">
        <button class="btn-primary" onclick="frOpenNew()">+ New Feature Request</button>
      </div>
    </div>
    <div class="qms-body">
      <div id="fr-toolbar"></div>
      <div id="fr-list-container"><div class="qms-loading"><div class="qms-spinner"></div> Loading feature requests…</div></div>
    </div>
  `;
  renderFRToolbar(filters);
  await frLoadList(filters);
}
window.frShowList = frShowList;

function renderFRToolbar(filters) {
  const meta = window.QMS_META || { feature_request_statuses: [], feature_request_priorities: [] };
  const el = document.getElementById("fr-toolbar");
  el.innerHTML = `
    <div class="qms-toolbar">
      <input type="text" id="fr-search" placeholder="Search by title, ID, or description…" value="${filters.q || ""}" />
      <select id="fr-filter-status">
        <option value="">All Statuses</option>
        ${qmsOptions(meta.feature_request_statuses, filters.status)}
      </select>
      <select id="fr-filter-priority">
        <option value="">All Priorities</option>
        ${qmsOptions(meta.feature_request_priorities, filters.priority)}
      </select>
      <button class="btn-secondary" onclick="frApplyFilters()">Filter</button>
    </div>
  `;
  document.getElementById("fr-search").addEventListener("keydown", e => {
    if (e.key === "Enter") frApplyFilters();
  });
}

function frApplyFilters() {
  const filters = {
    q: document.getElementById("fr-search").value.trim(),
    status: document.getElementById("fr-filter-status").value,
    priority: document.getElementById("fr-filter-priority").value,
  };
  frLoadList(filters);
}
window.frApplyFilters = frApplyFilters;

async function frLoadList(filters = {}) {
  const container = document.getElementById("fr-list-container");
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.status) params.set("status", filters.status);
  if (filters.priority) params.set("priority", filters.priority);

  try {
    const items = await qmsFetch(`/qms/feature-requests?${params.toString()}`);
    if (!items.length) {
      container.innerHTML = `
        <div class="qms-empty">
          <div class="qms-empty-icon"><span class='icon' data-lucide='lightbulb'></span></div>
          <h3>No feature requests yet</h3>
          <p>Create the first one with "+ New Feature Request".</p>
        </div>`;
      if (window.lucide) window.lucide.createIcons();
      return;
    }
    container.innerHTML = `
      <table class="qms-table">
        <thead><tr>
          <th>Feature ID</th><th>Title</th><th>Priority</th><th>Status</th>
          <th>Assigned To</th><th>Created By</th><th>Created Date</th><th></th>
        </tr></thead>
        <tbody>
          ${items.map(fr => `
            <tr class="clickable" onclick="frOpenEdit(${fr.id})">
              <td>${fr.fr_number}</td>
              <td>${fr.title}</td>
              <td>${qmsBadge(fr.priority)}</td>
              <td>${qmsBadge(fr.status)}</td>
              <td>${fr.assigned_to || "—"}</td>
              <td>${fr.created_by || "—"}</td>
              <td>${(fr.created_at || "").slice(0, 10)}</td>
              <td><a href="#" style="font-size:11px;color:#C35F5B" onclick="event.stopPropagation();frDelete(${fr.id},'${(fr.title || "").replace(/'/g, "\\'")}')">Delete</a></td>
            </tr>`).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    if (window.PharmaUI) window.PharmaUI.errorState(container, { message: `Failed to load feature requests: ${e.message}`, onRetry: () => frLoadList(filters) });
    else container.innerHTML = `<div class="qms-empty"><p>Failed to load feature requests: ${e.message}</p></div>`;
  }
}

// ── Create / Edit modal ────────────────────────────────────────────────────

function frModalHTML(fr) {
  const meta = window.QMS_META || { feature_request_modules: [], feature_request_priorities: [], feature_request_statuses: [] };
  const isEdit = !!fr;
  return `
    <div class="modal-header">
      <h2>${isEdit ? `Edit Feature Request — ${fr.fr_number}` : "New Feature Request"}</h2>
      <button class="modal-close" onclick="document.getElementById('fr-modal').remove()">&times;</button>
    </div>
    <div class="modal-body">
      <div class="form-grid">
        <div class="form-field span-2">
          <label>Title *</label>
          <input type="text" id="fr-title" value="${isEdit ? (fr.title || "").replace(/"/g, "&quot;") : ""}" placeholder="e.g. Add bulk export for CAPA reports" />
        </div>
        <div class="form-field span-2">
          <label>Description *</label>
          <textarea id="fr-description">${isEdit ? (fr.description || "") : ""}</textarea>
        </div>
        <div class="form-field">
          <label>Module</label>
          <select id="fr-module">${qmsOptions(meta.feature_request_modules, isEdit ? fr.module : "")}</select>
        </div>
        <div class="form-field">
          <label>Priority</label>
          <select id="fr-priority">${qmsOptions(meta.feature_request_priorities, isEdit ? fr.priority : "Medium")}</select>
        </div>
        ${isEdit ? `
        <div class="form-field">
          <label>Status</label>
          <select id="fr-status">${qmsOptions(meta.feature_request_statuses, fr.status)}</select>
        </div>` : ""}
        <div class="form-field">
          <label>Assigned To</label>
          <input type="text" id="fr-assigned-to" value="${isEdit ? (fr.assigned_to || "").replace(/"/g, "&quot;") : ""}" placeholder="Name" />
        </div>
        ${!isEdit ? `
        <div class="form-field span-2">
          <label>Attachment (optional)</label>
          <input type="file" id="fr-attachment" />
        </div>` : ""}
      </div>
      ${isEdit ? `<div id="fr-edit-attachments" style="margin-top:16px"><h3 style="font-size:13px;margin-bottom:8px">Attachments</h3><div id="qms-attachments-feature_request-${fr.id}"></div></div>` : ""}
    </div>
    <div class="modal-footer">
      <button class="btn-secondary" onclick="document.getElementById('fr-modal').remove()">Cancel</button>
      <button class="btn-primary" id="fr-save-btn" onclick="${isEdit ? `frUpdate(${fr.id})` : "frCreate()"}">${isEdit ? "Save Changes" : "Create Feature Request"}</button>
    </div>
  `;
}

function frOpenNew() {
  if (window.PharmaAuth && !window.PharmaAuth.requireCompanyContext()) return;
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";
  overlay.id = "fr-modal";
  overlay.innerHTML = `<div class="modal open qms-modal-lg">${frModalHTML(null)}</div>`;
  document.body.appendChild(overlay);
}
window.frOpenNew = frOpenNew;

async function frOpenEdit(id) {
  try {
    const fr = await qmsFetch(`/qms/feature-requests/${id}`);
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay open";
    overlay.id = "fr-modal";
    overlay.innerHTML = `<div class="modal open qms-modal-lg">${frModalHTML(fr)}</div>`;
    document.body.appendChild(overlay);
    qmsRenderAttachments(`qms-attachments-feature_request-${fr.id}`, "feature_request", fr.id);
  } catch (e) {
    qmsToast("Failed to load feature request: " + e.message);
  }
}
window.frOpenEdit = frOpenEdit;

async function frCreate() {
  const title = document.getElementById("fr-title").value.trim();
  const description = document.getElementById("fr-description").value.trim();
  if (!title) { qmsToast("Title is required"); return; }
  if (!description) { qmsToast("Description is required"); return; }
  const btn = document.getElementById("fr-save-btn");
  if (btn.disabled) return;
  btn.disabled = true;
  const data = {
    title,
    description,
    module: document.getElementById("fr-module").value,
    priority: document.getElementById("fr-priority").value,
    assigned_to: document.getElementById("fr-assigned-to").value.trim(),
  };
  try {
    const fr = await qmsPostJSON("/qms/feature-requests", data);
    const fileInput = document.getElementById("fr-attachment");
    if (fileInput && fileInput.files.length) {
      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      try {
        await qmsFetch(`/qms/feature_request/${fr.id}/attachments`, { method: "POST", body: fd });
      } catch (e) {
        qmsToast("Feature request created, but attachment upload failed: " + e.message);
      }
    }
    document.getElementById("fr-modal").remove();
    qmsToast(`Created ${fr.fr_number}`);
    frLoadList();
  } catch (e) {
    qmsToast("Failed to create feature request: " + e.message);
    btn.disabled = false;
  }
}
window.frCreate = frCreate;

async function frUpdate(id) {
  const title = document.getElementById("fr-title").value.trim();
  const description = document.getElementById("fr-description").value.trim();
  if (!title) { qmsToast("Title is required"); return; }
  if (!description) { qmsToast("Description is required"); return; }
  const btn = document.getElementById("fr-save-btn");
  if (btn.disabled) return;
  btn.disabled = true;
  const data = {
    title,
    description,
    module: document.getElementById("fr-module").value,
    priority: document.getElementById("fr-priority").value,
    status: document.getElementById("fr-status").value,
    assigned_to: document.getElementById("fr-assigned-to").value.trim(),
  };
  try {
    await qmsPutJSON(`/qms/feature-requests/${id}`, data);
    document.getElementById("fr-modal").remove();
    qmsToast("Saved");
    frLoadList();
  } catch (e) {
    qmsToast("Failed to save feature request: " + e.message);
    btn.disabled = false;
  }
}
window.frUpdate = frUpdate;

async function frDelete(id, title) {
  if (!confirm(`Delete feature request "${title}"? This cannot be undone.`)) return;
  try {
    await qmsFetch(`/qms/feature-requests/${id}`, { method: "DELETE" });
    qmsToast("Feature request deleted");
    frLoadList();
  } catch (e) {
    qmsToast("Delete failed: " + e.message);
  }
}
window.frDelete = frDelete;
