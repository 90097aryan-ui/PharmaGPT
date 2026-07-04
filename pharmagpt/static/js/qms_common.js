/*
 * qms_common.js — Shared frontend for the Quality Management Suite.
 *
 * Provides: sidebar collapse/nested-group toggles, a fetch wrapper, a status
 * badge helper, an SSE streaming helper, and reusable panel renderers
 * (Attachments / Comments / Audit Trail / Approval) used by all three
 * Phase 1 module scripts (qms_documents.js, qms_deviations.js, qms_capa.js)
 * instead of each re-implementing them. Reuses window.showToast (risk.js).
 */

// ── Fetch wrapper ──────────────────────────────────────────────────────────────

async function qmsFetch(url, opts = {}) {
  const res = await fetch(url, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { /* no JSON body */ }
  if (!res.ok) {
    const msg = (data && data.error) || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

async function qmsPostJSON(url, body) {
  return qmsFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

async function qmsPutJSON(url, body) {
  return qmsFetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

function qmsToast(msg) {
  if (window.showToast) window.showToast(msg);
}

// ── Sidebar: nested "Quality Management" section ──────────────────────────────

let qmsSectionOpen = true;
function toggleQMSSection() {
  const items = document.getElementById("qms-nav-items");
  const btn = document.getElementById("qms-collapse-btn");
  qmsSectionOpen = !qmsSectionOpen;
  items.style.display = qmsSectionOpen ? "block" : "none";
  if (btn) btn.textContent = qmsSectionOpen ? "▲" : "▼";
}
window.toggleQMSSection = toggleQMSSection;

const _qmsGroupState = {};
function toggleQMSGroup(groupId) {
  const items = document.getElementById(`qms-group-${groupId}`);
  const toggle = document.getElementById(`qms-group-toggle-${groupId}`);
  const open = _qmsGroupState[groupId] !== false;
  _qmsGroupState[groupId] = !open;
  if (items) items.style.display = !open ? "block" : "none";
  if (toggle) toggle.textContent = !open ? "▲" : "▼";
}
window.toggleQMSGroup = toggleQMSGroup;

// ── Status badge helper ────────────────────────────────────────────────────────

function qmsBadgeClass(status) {
  return "badge-" + String(status || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

function qmsBadge(status) {
  if (!status) return "";
  return `<span class="badge ${qmsBadgeClass(status)}">${status}</span>`;
}

// ── Meta (enum) cache ───────────────────────────────────────────────────────────

window.QMS_META = null;
async function qmsLoadMeta() {
  if (window.QMS_META) return window.QMS_META;
  window.QMS_META = await qmsFetch("/qms/meta");
  return window.QMS_META;
}
window.qmsLoadMeta = qmsLoadMeta;

function qmsOptions(values, selected) {
  return (values || []).map(v => `<option value="${v}" ${v === selected ? "selected" : ""}>${v}</option>`).join("");
}
window.qmsOptions = qmsOptions;

// ── SSE streaming helper ────────────────────────────────────────────────────────

async function qmsStream(url, body, { onChunk, onDone, onError } = {}) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!res.body) throw new Error("Streaming not supported by this browser");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let done = false;

    while (!done) {
      const { value, done: streamDone } = await reader.read();
      done = streamDone;
      if (value) {
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const event = JSON.parse(line.slice(6));
          if (event.error) { if (onError) onError(event.error); }
          else if (event.done) { if (onDone) onDone(event); }
          else if (event.chunk && onChunk) { onChunk(event.chunk); }
        }
      }
    }
  } catch (e) {
    if (onError) onError(e.message);
  }
}
window.qmsStream = qmsStream;

// ── Shared panels: Attachments / Comments / Audit Trail / Approval ────────────

async function qmsRenderAttachments(containerId, recordType, recordId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading attachments…</div>`;
  try {
    const attachments = await qmsFetch(`/qms/${recordType}/${recordId}/attachments`);
    el.innerHTML = `
      <div style="margin-bottom:12px">
        <input type="file" id="qms-attach-file-${recordType}-${recordId}" style="font-size:12px" />
        <input type="text" id="qms-attach-desc-${recordType}-${recordId}" placeholder="Description (optional)" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:12px;margin-left:6px" />
        <button class="btn-primary" style="padding:6px 14px;font-size:12px" onclick="qmsUploadAttachment('${recordType}',${recordId})">Upload</button>
      </div>
      ${attachments.length ? attachments.map(a => `
        <div class="qms-panel-item">
          <div>
            <span class="qms-attachment-icon">\u{1F4CE}</span>${a.original_name}
            ${a.description ? `<div class="qms-panel-item-meta">${a.description}</div>` : ""}
            <div class="qms-panel-item-meta">Uploaded by ${a.uploaded_by || "—"} · ${a.created_at}</div>
          </div>
          <div>
            <a href="/qms/attachments/${a.id}/download" style="font-size:11px;margin-right:10px">Download</a>
            <a href="#" style="font-size:11px;color:#C62828" onclick="qmsDeleteAttachment('${recordType}',${recordId},${a.id});return false;">Delete</a>
          </div>
        </div>`).join("") : `<div class="qms-panel-item-meta">No attachments yet.</div>`}
    `;
  } catch (e) {
    el.innerHTML = `<div class="qms-panel-item-meta">Failed to load attachments: ${e.message}</div>`;
  }
}
window.qmsRenderAttachments = qmsRenderAttachments;

async function qmsUploadAttachment(recordType, recordId) {
  const fileInput = document.getElementById(`qms-attach-file-${recordType}-${recordId}`);
  const descInput = document.getElementById(`qms-attach-desc-${recordType}-${recordId}`);
  if (!fileInput.files.length) { qmsToast("Choose a file first"); return; }
  const fd = new FormData();
  fd.append("file", fileInput.files[0]);
  fd.append("description", descInput ? descInput.value : "");
  try {
    await qmsFetch(`/qms/${recordType}/${recordId}/attachments`, { method: "POST", body: fd });
    qmsToast("Attachment uploaded");
    qmsRenderAttachments(`qms-attachments-${recordType}-${recordId}`, recordType, recordId);
  } catch (e) {
    qmsToast("Upload failed: " + e.message);
  }
}
window.qmsUploadAttachment = qmsUploadAttachment;

async function qmsDeleteAttachment(recordType, recordId, attachmentId) {
  try {
    await qmsFetch(`/qms/attachments/${attachmentId}`, { method: "DELETE" });
    qmsRenderAttachments(`qms-attachments-${recordType}-${recordId}`, recordType, recordId);
  } catch (e) {
    qmsToast("Delete failed: " + e.message);
  }
}
window.qmsDeleteAttachment = qmsDeleteAttachment;

async function qmsRenderComments(containerId, recordType, recordId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading comments…</div>`;
  try {
    const comments = await qmsFetch(`/qms/${recordType}/${recordId}/comments`);
    el.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:14px">
        <input type="text" id="qms-comment-author-${recordType}-${recordId}" placeholder="Your name" style="flex:0 0 140px;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:12px" />
        <input type="text" id="qms-comment-text-${recordType}-${recordId}" placeholder="Add a comment…" style="flex:1;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:12px" />
        <button class="btn-primary" style="padding:8px 14px;font-size:12px" onclick="qmsAddComment('${recordType}',${recordId})">Post</button>
      </div>
      ${comments.length ? comments.map(c => `
        <div class="qms-panel-item">
          <div>
            <strong>${c.author || "Anonymous"}</strong>${c.role ? ` <span class="qms-panel-item-meta">(${c.role})</span>` : ""}
            <div>${c.comment}</div>
            <div class="qms-panel-item-meta">${c.created_at}</div>
          </div>
        </div>`).join("") : `<div class="qms-panel-item-meta">No comments yet.</div>`}
    `;
  } catch (e) {
    el.innerHTML = `<div class="qms-panel-item-meta">Failed to load comments: ${e.message}</div>`;
  }
}
window.qmsRenderComments = qmsRenderComments;

async function qmsAddComment(recordType, recordId) {
  const author = document.getElementById(`qms-comment-author-${recordType}-${recordId}`).value.trim();
  const text = document.getElementById(`qms-comment-text-${recordType}-${recordId}`).value.trim();
  if (!text) { qmsToast("Comment text is required"); return; }
  try {
    await qmsPostJSON(`/qms/${recordType}/${recordId}/comments`, { author, comment: text });
    qmsRenderComments(`qms-comments-${recordType}-${recordId}`, recordType, recordId);
  } catch (e) {
    qmsToast("Failed to post comment: " + e.message);
  }
}
window.qmsAddComment = qmsAddComment;

async function qmsRenderAuditTrail(containerId, recordType, recordId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading audit trail…</div>`;
  try {
    const entries = await qmsFetch(`/qms/${recordType}/${recordId}/audit-trail`);
    el.innerHTML = entries.length ? entries.map(e => `
      <div class="qms-panel-item">
        <div>
          <span class="qms-audit-action">${e.action}</span>
          ${e.detail ? ` — ${e.detail}` : ""}
          <div class="qms-panel-item-meta">${e.performed_by || "System"} · ${e.created_at}</div>
        </div>
      </div>`).join("") : `<div class="qms-panel-item-meta">No audit trail entries yet.</div>`;
  } catch (e) {
    el.innerHTML = `<div class="qms-panel-item-meta">Failed to load audit trail: ${e.message}</div>`;
  }
}
window.qmsRenderAuditTrail = qmsRenderAuditTrail;

/**
 * Renders the approval / e-signature trail plus a small form. The caller
 * supplies the list of allowed actions (module-specific status vocabulary)
 * and the POST url that applies the status transition — each module route
 * owns that logic (see routes/qms_documents.py::submit_approval).
 */
async function qmsRenderApproval(containerId, recordType, recordId, actions, postUrl, onSubmitted) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading approval trail…</div>`;
  try {
    const entries = await qmsFetch(`/qms/${recordType}/${recordId}/approval`);
    const formId = `qms-approval-form-${recordType}-${recordId}`;
    el.innerHTML = `
      <div class="qms-section-card" style="margin-bottom:14px">
        <h3>Record Approval Action</h3>
        <div class="form-grid cols-3">
          <div class="form-field">
            <label>Action</label>
            <select id="${formId}-action">${qmsOptions(actions)}</select>
          </div>
          <div class="form-field">
            <label>Performed By (typed e-signature)</label>
            <input type="text" id="${formId}-name" placeholder="Full name" />
          </div>
          <div class="form-field">
            <label>Role</label>
            <input type="text" id="${formId}-role" placeholder="e.g. QA Manager" />
          </div>
          <div class="form-field span-2">
            <label>Comments</label>
            <input type="text" id="${formId}-comments" placeholder="Optional comments" />
          </div>
        </div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsSubmitApproval('${formId}','${postUrl}','${containerId}','${recordType}',${recordId})">Submit</button>
        </div>
      </div>
      ${entries.length ? entries.map(a => `
        <div class="qms-panel-item">
          <div>
            <span class="qms-audit-action">${a.action}</span>
            <div class="qms-panel-item-meta">${a.performed_by || ""}${a.role ? ` (${a.role})` : ""} · ${a.created_at}</div>
            ${a.comments ? `<div>${a.comments}</div>` : ""}
          </div>
        </div>`).join("") : `<div class="qms-panel-item-meta">No approval actions recorded yet.</div>`}
    `;
    if (onSubmitted) window._qmsApprovalCallbacks[containerId] = onSubmitted;
  } catch (e) {
    el.innerHTML = `<div class="qms-panel-item-meta">Failed to load approval trail: ${e.message}</div>`;
  }
}
window.qmsRenderApproval = qmsRenderApproval;

window._qmsApprovalCallbacks = {};
async function qmsSubmitApproval(formId, postUrl, containerId, recordType, recordId) {
  const action = document.getElementById(`${formId}-action`).value;
  const performed_by = document.getElementById(`${formId}-name`).value.trim();
  const role = document.getElementById(`${formId}-role`).value.trim();
  const comments = document.getElementById(`${formId}-comments`).value.trim();
  if (!performed_by) { qmsToast("Typed e-signature (name) is required"); return; }
  try {
    await qmsPostJSON(postUrl, { action, performed_by, role, comments, electronic_sig: performed_by });
    qmsToast(`Recorded: ${action}`);
    const cb = window._qmsApprovalCallbacks[containerId];
    if (cb) cb();
  } catch (e) {
    qmsToast("Failed to record approval: " + e.message);
  }
}
window.qmsSubmitApproval = qmsSubmitApproval;

// ── Unified QMS Dashboard (cross-module overview) ──────────────────────────────

async function initQMSDashboard() {
  const body = document.getElementById("qms-dashboard-body");
  body.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading QMS dashboard…</div>`;
  try {
    const stats = await qmsFetch("/qms/dashboard");
    const s = stats.summary;
    body.innerHTML = `
      <div class="qms-page-header">
        <div>
          <h2>Quality Management Suite — Dashboard</h2>
          <p>Document Control · Deviation Management · CAPA — unified overview</p>
        </div>
      </div>
      <div class="qms-body">
        <div class="qms-stats-grid">
          <div class="qms-stat-card info"><div class="qms-stat-value">${s.total_documents}</div><div class="qms-stat-label">Controlled Documents</div></div>
          <div class="qms-stat-card warning"><div class="qms-stat-value">${s.docs_due_for_review}</div><div class="qms-stat-label">Docs Due for Review</div></div>
          <div class="qms-stat-card critical"><div class="qms-stat-value">${s.open_deviations}</div><div class="qms-stat-label">Open Deviations</div></div>
          <div class="qms-stat-card info"><div class="qms-stat-value">${s.total_deviations}</div><div class="qms-stat-label">Total Deviations</div></div>
          <div class="qms-stat-card warning"><div class="qms-stat-value">${s.open_capas}</div><div class="qms-stat-label">Open CAPAs</div></div>
          <div class="qms-stat-card critical"><div class="qms-stat-value">${s.overdue_capas}</div><div class="qms-stat-label">Overdue CAPAs</div></div>
        </div>

        <div class="qms-section-card">
          <h3>📄 Document Control</h3>
          <p style="font-size:12.5px;color:var(--text-muted)">
            Draft: ${stats.documents.draft} · Under Review: ${stats.documents.under_review} ·
            Pending Approval: ${stats.documents.pending_approval} · Effective: ${stats.documents.effective} ·
            Obsolete: ${stats.documents.obsolete}
          </p>
          <button class="btn-secondary" onclick="document.getElementById('nav-qms-documents').click()">Open Document Control &rarr;</button>
        </div>

        <div class="qms-section-card">
          <h3>⚡ Deviation Management</h3>
          <p style="font-size:12.5px;color:var(--text-muted)">
            Open: ${stats.deviations.open} · Closed: ${stats.deviations.closed} · Total: ${stats.deviations.total}
          </p>
          <button class="btn-secondary" onclick="document.getElementById('nav-qms-deviations') && document.getElementById('nav-qms-deviations').click()">Open Deviations &rarr;</button>
        </div>

        <div class="qms-section-card">
          <h3>🔄 CAPA</h3>
          <p style="font-size:12.5px;color:var(--text-muted)">
            Open: ${stats.capa.open} · Closed: ${stats.capa.closed} · Overdue: ${stats.capa.overdue} ·
            Escalated Actions: ${stats.capa.escalated_actions || 0}
          </p>
          <button class="btn-secondary" onclick="document.getElementById('nav-qms-capa') && document.getElementById('nav-qms-capa').click()">Open CAPA &rarr;</button>
        </div>
      </div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="qms-empty"><p>Failed to load QMS dashboard: ${e.message}</p></div>`;
  }
}
window.initQMSDashboard = initQMSDashboard;
