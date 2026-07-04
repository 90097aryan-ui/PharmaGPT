/*
 * qms_documents.js — Document Control module frontend.
 *
 * Renders entirely into <main id="view-qms-documents"><div id="qms-documents-body">.
 * Uses the shared helpers in qms_common.js (qmsFetch, qmsStream, qmsBadge,
 * qmsRenderAttachments/Comments/AuditTrail/Approval) rather than
 * re-implementing them.
 */

let qmsDocCurrentId = null;
let qmsDocActiveTab = "overview";

function initQMSDocuments() {
  qmsLoadMeta().then(() => qmsDocShowList());
}
window.initQMSDocuments = initQMSDocuments;

// ── List view ───────────────────────────────────────────────────────────────

async function qmsDocShowList(filters = {}) {
  qmsDocCurrentId = null;
  const body = document.getElementById("qms-documents-body");
  body.innerHTML = `
    <div class="qms-page-header">
      <div>
        <h2>Document Control</h2>
        <p>SOPs, Protocols, Specifications, and controlled documents — lifecycle, versioning, and training</p>
      </div>
      <div class="qms-header-actions">
        <button class="btn-primary" onclick="qmsDocOpenNew()">+ New Document</button>
      </div>
    </div>
    <div class="qms-body">
      <div id="qms-doc-toolbar"></div>
      <div id="qms-doc-list-container"><div class="qms-loading"><div class="qms-spinner"></div> Loading documents…</div></div>
    </div>
  `;
  renderQMSDocToolbar(filters);
  await qmsDocLoadList(filters);
}
window.qmsDocShowList = qmsDocShowList;

function renderQMSDocToolbar(filters) {
  const meta = window.QMS_META || { document_types: [], document_statuses: [] };
  const el = document.getElementById("qms-doc-toolbar");
  el.innerHTML = `
    <div class="qms-toolbar">
      <input type="text" id="qms-doc-search" placeholder="Search by title, number, or content…" value="${filters.q || ""}" />
      <select id="qms-doc-filter-type">
        <option value="">All Types</option>
        ${qmsOptions(meta.document_types, filters.type)}
      </select>
      <select id="qms-doc-filter-status">
        <option value="">All Statuses</option>
        ${qmsOptions(meta.document_statuses, filters.status)}
      </select>
      <button class="btn-secondary" onclick="qmsDocApplyFilters()">Filter</button>
    </div>
  `;
  document.getElementById("qms-doc-search").addEventListener("keydown", e => {
    if (e.key === "Enter") qmsDocApplyFilters();
  });
}

function qmsDocApplyFilters() {
  const filters = {
    q: document.getElementById("qms-doc-search").value.trim(),
    type: document.getElementById("qms-doc-filter-type").value,
    status: document.getElementById("qms-doc-filter-status").value,
  };
  qmsDocLoadList(filters);
}
window.qmsDocApplyFilters = qmsDocApplyFilters;

async function qmsDocLoadList(filters = {}) {
  const container = document.getElementById("qms-doc-list-container");
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.type) params.set("type", filters.type);
  if (filters.status) params.set("status", filters.status);

  try {
    const docs = await qmsFetch(`/qms/documents?${params.toString()}`);
    if (!docs.length) {
      container.innerHTML = `
        <div class="qms-empty">
          <div class="qms-empty-icon">📄</div>
          <h3>No documents yet</h3>
          <p>Create your first controlled document to get started.</p>
        </div>`;
      return;
    }
    container.innerHTML = `
      <table class="qms-table">
        <thead><tr><th>Doc Number</th><th>Title</th><th>Type</th><th>Department</th><th>Version</th><th>Status</th><th>Effective Date</th></tr></thead>
        <tbody>
          ${docs.map(d => `
            <tr class="clickable" onclick="qmsDocOpenDetail(${d.id})">
              <td>${d.doc_number}</td>
              <td>${d.title}</td>
              <td>${d.doc_type}</td>
              <td>${d.department || "—"}</td>
              <td>${d.version}</td>
              <td>${qmsBadge(d.status)}</td>
              <td>${d.effective_date || "—"}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    container.innerHTML = `<div class="qms-empty"><p>Failed to load documents: ${e.message}</p></div>`;
  }
}

// ── Create wizard ───────────────────────────────────────────────────────────

function qmsDocOpenNew() {
  const meta = window.QMS_META || { document_types: [] };
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";
  overlay.id = "qms-doc-new-modal";
  overlay.innerHTML = `
    <div class="modal open qms-modal-lg">
      <div class="modal-header">
        <h2>New Controlled Document</h2>
        <button class="modal-close" onclick="document.getElementById('qms-doc-new-modal').remove()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="form-field span-2">
            <label>Title</label>
            <input type="text" id="qms-new-doc-title" placeholder="e.g. Cleaning of Tablet Compression Machine" />
          </div>
          <div class="form-field">
            <label>Document Type</label>
            <select id="qms-new-doc-type">${qmsOptions(meta.document_types, "SOP")}</select>
          </div>
          <div class="form-field">
            <label>Department</label>
            <input type="text" id="qms-new-doc-dept" placeholder="e.g. Quality Assurance" />
          </div>
          <div class="form-field">
            <label>Category</label>
            <input type="text" id="qms-new-doc-category" placeholder="Optional" />
          </div>
          <div class="form-field">
            <label>Owner</label>
            <input type="text" id="qms-new-doc-owner" placeholder="Document owner" />
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="document.getElementById('qms-doc-new-modal').remove()">Cancel</button>
        <button class="btn-primary" onclick="qmsDocCreate()">Create Document</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}
window.qmsDocOpenNew = qmsDocOpenNew;

async function qmsDocCreate() {
  const title = document.getElementById("qms-new-doc-title").value.trim();
  if (!title) { qmsToast("Title is required"); return; }
  const data = {
    title,
    doc_type: document.getElementById("qms-new-doc-type").value,
    department: document.getElementById("qms-new-doc-dept").value.trim(),
    category: document.getElementById("qms-new-doc-category").value.trim(),
    owner: document.getElementById("qms-new-doc-owner").value.trim(),
  };
  try {
    const doc = await qmsPostJSON("/qms/documents", data);
    document.getElementById("qms-doc-new-modal").remove();
    qmsToast(`Created ${doc.doc_number}`);
    qmsDocOpenDetail(doc.id);
  } catch (e) {
    qmsToast("Failed to create document: " + e.message);
  }
}
window.qmsDocCreate = qmsDocCreate;

// ── Detail view ─────────────────────────────────────────────────────────────

async function qmsDocOpenDetail(id) {
  qmsDocCurrentId = id;
  qmsDocActiveTab = "overview";
  const body = document.getElementById("qms-documents-body");
  body.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading document…</div>`;
  try {
    const doc = await qmsFetch(`/qms/documents/${id}`);
    body.innerHTML = `
      <div class="qms-page-header">
        <div>
          <button class="btn-secondary" style="margin-bottom:10px;padding:5px 12px;font-size:12px" onclick="qmsDocShowList()">&larr; All Documents</button>
          <div class="qms-detail-number">${doc.doc_number} · ${doc.doc_type}</div>
          <div class="qms-detail-title">${doc.title}</div>
          <div class="qms-detail-meta">
            <span>${qmsBadge(doc.status)}</span>
            <span>Version ${doc.version}</span>
            <span>Department: ${doc.department || "—"}</span>
            <span>Owner: ${doc.owner || "—"}</span>
          </div>
        </div>
        <div class="qms-header-actions">
          <button class="btn-secondary" onclick="qmsDocPrint(${id})">Print</button>
          <button class="btn-secondary" onclick="qmsDocExportDocx(${id})">Export DOCX</button>
        </div>
      </div>
      <div class="qms-body">
        <div class="qms-tabs" id="qms-doc-tabs">
          ${["overview", "content", "versions", "training", "distribution", "attachments", "comments", "audit", "approval"]
            .map(t => `<button class="qms-tab ${t === qmsDocActiveTab ? "active" : ""}" onclick="qmsDocSwitchTab('${t}')">${qmsDocTabLabel(t)}</button>`).join("")}
        </div>
        <div id="qms-doc-tab-body"></div>
      </div>
    `;
    qmsDocRenderTab(doc);
  } catch (e) {
    body.innerHTML = `<div class="qms-empty"><p>Failed to load document: ${e.message}</p></div>`;
  }
}
window.qmsDocOpenDetail = qmsDocOpenDetail;

function qmsDocTabLabel(t) {
  return {
    overview: "Overview", content: "Content / AI Draft", versions: "Version History",
    training: "Training", distribution: "Distribution", attachments: "Attachments",
    comments: "Comments", audit: "Audit Trail", approval: "Approval",
  }[t] || t;
}

async function qmsDocSwitchTab(tab) {
  qmsDocActiveTab = tab;
  document.querySelectorAll("#qms-doc-tabs .qms-tab").forEach(b => b.classList.remove("active"));
  const idx = ["overview", "content", "versions", "training", "distribution", "attachments", "comments", "audit", "approval"].indexOf(tab);
  const btns = document.querySelectorAll("#qms-doc-tabs .qms-tab");
  if (btns[idx]) btns[idx].classList.add("active");
  const doc = await qmsFetch(`/qms/documents/${qmsDocCurrentId}`);
  qmsDocRenderTab(doc);
}
window.qmsDocSwitchTab = qmsDocSwitchTab;

function qmsDocRenderTab(doc) {
  const el = document.getElementById("qms-doc-tab-body");
  const id = doc.id;

  if (qmsDocActiveTab === "overview") {
    el.innerHTML = `
      <div class="qms-section-card">
        <h3>Document Control Information</h3>
        <div class="form-grid">
          <div class="form-field"><label>Version</label><input type="text" id="qms-ov-version" value="${doc.version}" /></div>
          <div class="form-field"><label>Status</label><input type="text" value="${doc.status}" disabled /></div>
          <div class="form-field"><label>Effective Date</label><input type="date" id="qms-ov-effective" value="${doc.effective_date || ""}" /></div>
          <div class="form-field"><label>Review Date</label><input type="date" id="qms-ov-review" value="${doc.review_date || ""}" /></div>
          <div class="form-field"><label>Expiry Date</label><input type="date" id="qms-ov-expiry" value="${doc.expiry_date || ""}" /></div>
          <div class="form-field"><label>Owner</label><input type="text" id="qms-ov-owner" value="${doc.owner || ""}" /></div>
          <div class="form-field"><label>Reviewer</label><input type="text" id="qms-ov-reviewer" value="${doc.reviewer || ""}" /></div>
          <div class="form-field"><label>Approver</label><input type="text" id="qms-ov-approver" value="${doc.approver || ""}" /></div>
        </div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsDocSaveOverview(${id})">Save</button>
        </div>
      </div>
    `;
  } else if (qmsDocActiveTab === "content") {
    el.innerHTML = `
      <div class="qms-section-card">
        <h3>AI Draft Generation</h3>
        <p style="font-size:12.5px;color:var(--text-muted);margin-bottom:12px">
          Generates complete ${doc.doc_type} content (Purpose, Scope, Responsibilities, Procedure, Acceptance Criteria, References) using the PharmaGPT regulatory persona.
        </p>
        <div class="qms-form-actions" style="justify-content:flex-start;margin-top:0;margin-bottom:14px">
          <button class="btn-primary" id="qms-doc-generate-btn" onclick="qmsDocGenerateDraft(${id})">✨ Generate Draft with AI</button>
          <button class="btn-secondary" id="qms-doc-review-btn" onclick="qmsDocRunReview(${id})">Run Regulatory Compliance Review</button>
        </div>
        <div id="qms-doc-review-result"></div>
        <textarea id="qms-doc-content-editor" style="width:100%;min-height:400px;font-family:monospace;font-size:12px;padding:14px;border:1px solid var(--border);border-radius:6px" placeholder="Document content (markdown)…">${doc.content || ""}</textarea>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsDocSaveContent(${id})">Save Content</button>
        </div>
      </div>
    `;
    if (doc.ai_review_data && doc.ai_review_data.overall_score) {
      qmsDocRenderReview(doc.ai_review_data);
    }
  } else if (qmsDocActiveTab === "versions") {
    qmsDocRenderVersions(id);
  } else if (qmsDocActiveTab === "training") {
    qmsDocRenderTraining(id);
  } else if (qmsDocActiveTab === "distribution") {
    qmsDocRenderDistribution(id);
  } else if (qmsDocActiveTab === "attachments") {
    el.innerHTML = `<div id="qms-attachments-document-${id}"></div>`;
    qmsRenderAttachments(`qms-attachments-document-${id}`, "document", id);
  } else if (qmsDocActiveTab === "comments") {
    el.innerHTML = `<div id="qms-comments-document-${id}"></div>`;
    qmsRenderComments(`qms-comments-document-${id}`, "document", id);
  } else if (qmsDocActiveTab === "audit") {
    el.innerHTML = `<div id="qms-audit-document-${id}"></div>`;
    qmsRenderAuditTrail(`qms-audit-document-${id}`, "document", id);
  } else if (qmsDocActiveTab === "approval") {
    el.innerHTML = `<div id="qms-approval-document-${id}"></div>`;
    const actions = ["Submitted for Review", "Reviewed", "Submitted for Approval", "Approved", "Rejected", "Send for Revision", "Made Obsolete"];
    qmsRenderApproval(`qms-approval-document-${id}`, "document", id, actions, `/qms/documents/${id}/approval`,
      () => qmsDocRefreshApprovalTab(id));
  }
}

async function qmsDocRefreshApprovalTab(id) {
  const doc = await qmsFetch(`/qms/documents/${id}`);
  const metaEl = document.querySelector(".qms-detail-meta");
  if (metaEl) {
    metaEl.innerHTML = `
      <span>${qmsBadge(doc.status)}</span>
      <span>Version ${doc.version}</span>
      <span>Department: ${doc.department || "—"}</span>
      <span>Owner: ${doc.owner || "—"}</span>
    `;
  }
  const actions = ["Submitted for Review", "Reviewed", "Submitted for Approval", "Approved", "Rejected", "Send for Revision", "Made Obsolete"];
  qmsRenderApproval(`qms-approval-document-${id}`, "document", id, actions, `/qms/documents/${id}/approval`,
    () => qmsDocRefreshApprovalTab(id));
}

async function qmsDocSaveOverview(id) {
  const data = {
    version: document.getElementById("qms-ov-version").value.trim(),
    effective_date: document.getElementById("qms-ov-effective").value,
    review_date: document.getElementById("qms-ov-review").value,
    expiry_date: document.getElementById("qms-ov-expiry").value,
    owner: document.getElementById("qms-ov-owner").value.trim(),
    reviewer: document.getElementById("qms-ov-reviewer").value.trim(),
    approver: document.getElementById("qms-ov-approver").value.trim(),
  };
  try {
    await qmsPutJSON(`/qms/documents/${id}`, data);
    qmsToast("Saved");
  } catch (e) {
    qmsToast("Save failed: " + e.message);
  }
}
window.qmsDocSaveOverview = qmsDocSaveOverview;

async function qmsDocSaveContent(id) {
  const content = document.getElementById("qms-doc-content-editor").value;
  try {
    await qmsPutJSON(`/qms/documents/${id}`, { content });
    qmsToast("Content saved");
  } catch (e) {
    qmsToast("Save failed: " + e.message);
  }
}
window.qmsDocSaveContent = qmsDocSaveContent;

function qmsDocGenerateDraft(id) {
  const editor = document.getElementById("qms-doc-content-editor");
  const reviewBtn = document.getElementById("qms-doc-review-btn");
  const genBtn = document.getElementById("qms-doc-generate-btn");
  editor.value = "";
  editor.disabled = true;
  if (reviewBtn) reviewBtn.disabled = true;
  if (genBtn) genBtn.disabled = true;
  qmsToast("Generating draft…");
  qmsStream(`/qms/documents/${id}/generate`, {}, {
    onChunk: chunk => { editor.value += chunk; editor.scrollTop = editor.scrollHeight; },
    onDone: () => {
      editor.disabled = false;
      if (reviewBtn) reviewBtn.disabled = false;
      if (genBtn) genBtn.disabled = false;
      qmsToast("Draft generated");
    },
    onError: err => {
      editor.disabled = false;
      if (reviewBtn) reviewBtn.disabled = false;
      if (genBtn) genBtn.disabled = false;
      qmsToast("Generation failed: " + err);
    },
  });
}
window.qmsDocGenerateDraft = qmsDocGenerateDraft;

async function qmsDocRunReview(id) {
  qmsToast("Running AI compliance review…");
  try {
    const review = await qmsPostJSON(`/qms/documents/${id}/review`, {});
    qmsDocRenderReview(review);
    qmsToast("Review complete");
  } catch (e) {
    qmsToast("Review failed: " + e.message);
  }
}
window.qmsDocRunReview = qmsDocRunReview;

function qmsDocRenderReview(review) {
  const el = document.getElementById("qms-doc-review-result");
  if (!el) return;
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>AI Regulatory Compliance Review</h3>
      <div class="qms-stats-grid">
        <div class="qms-stat-card info"><div class="qms-stat-value">${review.completeness_score ?? "—"}</div><div class="qms-stat-label">Completeness</div></div>
        <div class="qms-stat-card info"><div class="qms-stat-value">${review.regulatory_compliance_score ?? "—"}</div><div class="qms-stat-label">Regulatory Compliance</div></div>
        <div class="qms-stat-card info"><div class="qms-stat-value">${review.clarity_score ?? "—"}</div><div class="qms-stat-label">Clarity</div></div>
        <div class="qms-stat-card success"><div class="qms-stat-value">${review.overall_score ?? "—"}</div><div class="qms-stat-label">Overall — ${review.recommendation || ""}</div></div>
      </div>
      ${review.critical_findings && review.critical_findings.length ? `<p><strong>Findings:</strong> ${review.critical_findings.join("; ")}</p>` : ""}
      ${review.reviewer_comments ? `<p>${review.reviewer_comments}</p>` : ""}
    </div>
  `;
}

async function qmsDocRenderVersions(id) {
  const el = document.getElementById("qms-doc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading versions…</div>`;
  const versions = await qmsFetch(`/qms/documents/${id}/versions`);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Create New Version</h3>
      <div class="form-grid cols-3">
        <div class="form-field"><label>New Version Label</label><input type="text" id="qms-newver-label" placeholder="e.g. 2.0" /></div>
        <div class="form-field span-2"><label>Change Summary</label><input type="text" id="qms-newver-summary" placeholder="What changed" /></div>
      </div>
      <div class="qms-form-actions">
        <button class="btn-primary" onclick="qmsDocCreateVersion(${id})">Snapshot Current Content as New Version</button>
      </div>
    </div>
    ${versions.length ? `
      <table class="qms-table">
        <thead><tr><th>Version</th><th>Change Summary</th><th>Changed By</th><th>Date</th></tr></thead>
        <tbody>${versions.map(v => `<tr><td>${v.version}</td><td>${v.change_summary || "—"}</td><td>${v.changed_by || "—"}</td><td>${v.created_at}</td></tr>`).join("")}</tbody>
      </table>` : `<div class="qms-empty"><p>No prior versions recorded.</p></div>`}
  `;
}

async function qmsDocCreateVersion(id) {
  const version = document.getElementById("qms-newver-label").value.trim();
  const change_summary = document.getElementById("qms-newver-summary").value.trim();
  if (!version) { qmsToast("Version label is required"); return; }
  try {
    await qmsPostJSON(`/qms/documents/${id}/versions`, { version, change_summary, changed_by: "" });
    qmsToast("New version created");
    qmsDocRenderVersions(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDocCreateVersion = qmsDocCreateVersion;

async function qmsDocRenderTraining(id) {
  const el = document.getElementById("qms-doc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading training records…</div>`;
  const records = await qmsFetch(`/qms/documents/${id}/training`);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Add Training Requirement</h3>
      <div class="form-grid cols-3">
        <div class="form-field"><label>Trainee Name</label><input type="text" id="qms-train-name" /></div>
        <div class="form-field"><label>Role</label><input type="text" id="qms-train-role" /></div>
        <div class="form-field"><label>Trainer</label><input type="text" id="qms-train-trainer" /></div>
      </div>
      <div class="qms-form-actions">
        <button class="btn-primary" onclick="qmsDocAddTraining(${id})">Add</button>
      </div>
    </div>
    ${records.length ? `
      <table class="qms-table">
        <thead><tr><th>Trainee</th><th>Role</th><th>Status</th><th>Trainer</th><th>Date</th><th></th></tr></thead>
        <tbody>${records.map(r => `
          <tr>
            <td>${r.trainee_name}</td><td>${r.role || "—"}</td><td>${qmsBadge(r.training_status)}</td>
            <td>${r.trainer || "—"}</td><td>${r.training_date || "—"}</td>
            <td>${r.training_status !== "Completed" ? `<a href="#" onclick="qmsDocCompleteTraining(${id},${r.id});return false;">Mark Complete</a>` : ""}</td>
          </tr>`).join("")}</tbody>
      </table>` : `<div class="qms-empty"><p>No training records yet.</p></div>`}
  `;
}

async function qmsDocAddTraining(id) {
  const trainee_name = document.getElementById("qms-train-name").value.trim();
  if (!trainee_name) { qmsToast("Trainee name is required"); return; }
  const data = {
    trainee_name,
    role: document.getElementById("qms-train-role").value.trim(),
    trainer: document.getElementById("qms-train-trainer").value.trim(),
  };
  try {
    await qmsPostJSON(`/qms/documents/${id}/training`, data);
    qmsDocRenderTraining(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDocAddTraining = qmsDocAddTraining;

async function qmsDocCompleteTraining(docId, trainingId) {
  const today = new Date().toISOString().slice(0, 10);
  try {
    await qmsPutJSON(`/qms/documents/training/${trainingId}`, { training_status: "Completed", training_date: today });
    qmsDocRenderTraining(docId);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDocCompleteTraining = qmsDocCompleteTraining;

async function qmsDocRenderDistribution(id) {
  const el = document.getElementById("qms-doc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading distribution…</div>`;
  const records = await qmsFetch(`/qms/documents/${id}/distribution`);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Add Distribution</h3>
      <div class="form-grid cols-3">
        <div class="form-field"><label>Distributed To</label><input type="text" id="qms-dist-to" /></div>
        <div class="form-field"><label>Department</label><input type="text" id="qms-dist-dept" /></div>
        <div class="form-field"><label>Date</label><input type="date" id="qms-dist-date" /></div>
      </div>
      <div class="qms-form-actions">
        <button class="btn-primary" onclick="qmsDocAddDistribution(${id})">Add</button>
      </div>
    </div>
    ${records.length ? `
      <table class="qms-table">
        <thead><tr><th>Distributed To</th><th>Department</th><th>Date</th><th>Acknowledged</th><th></th></tr></thead>
        <tbody>${records.map(r => `
          <tr>
            <td>${r.distributed_to}</td><td>${r.department || "—"}</td><td>${r.distributed_date || "—"}</td>
            <td>${r.acknowledged ? "Yes — " + r.acknowledged_date : "No"}</td>
            <td>${!r.acknowledged ? `<a href="#" onclick="qmsDocAcknowledgeDistribution(${id},${r.id});return false;">Acknowledge</a>` : ""}</td>
          </tr>`).join("")}</tbody>
      </table>` : `<div class="qms-empty"><p>Not yet distributed.</p></div>`}
  `;
}

async function qmsDocAddDistribution(id) {
  const distributed_to = document.getElementById("qms-dist-to").value.trim();
  if (!distributed_to) { qmsToast("Recipient is required"); return; }
  const data = {
    distributed_to,
    department: document.getElementById("qms-dist-dept").value.trim(),
    distributed_date: document.getElementById("qms-dist-date").value,
  };
  try {
    await qmsPostJSON(`/qms/documents/${id}/distribution`, data);
    qmsDocRenderDistribution(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDocAddDistribution = qmsDocAddDistribution;

async function qmsDocAcknowledgeDistribution(docId, distId) {
  const today = new Date().toISOString().slice(0, 10);
  try {
    await qmsPostJSON(`/qms/documents/distribution/${distId}/acknowledge`, { acknowledged_date: today });
    qmsDocRenderDistribution(docId);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDocAcknowledgeDistribution = qmsDocAcknowledgeDistribution;

// ── Print / Export ──────────────────────────────────────────────────────────

async function qmsDocPrint(id) {
  try {
    const { markdown, title } = await qmsFetch(`/qms/documents/${id}/report`);
    const win = window.open("", "_blank");
    win.document.write(`<html><head><title>${title}</title></head><body>${window.marked ? marked.parse(markdown) : `<pre>${markdown}</pre>`}</body></html>`);
    win.document.close();
    win.print();
  } catch (e) {
    qmsToast("Failed to prepare print view: " + e.message);
  }
}
window.qmsDocPrint = qmsDocPrint;

async function qmsDocExportDocx(id) {
  try {
    const res = await fetch(`/qms/documents/${id}/export/docx`, { method: "POST" });
    if (!res.ok) { qmsToast("Export failed"); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `Document_${id}.docx`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    qmsToast("Export error: " + e.message);
  }
}
window.qmsDocExportDocx = qmsDocExportDocx;
