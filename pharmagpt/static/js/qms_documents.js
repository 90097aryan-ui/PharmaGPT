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
        ${((window.PharmaAuth && window.PharmaAuth.getUser()) || {}).role === "company_admin"
          ? `<button class="btn-secondary" onclick="qmsDocOpenApproverPoolSettings()">Configure Approver Pool</button>` : ""}
        <button class="btn-primary" onclick="qmsDocOpenNewSOP()">+ New SOP</button>
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
          <div class="qms-empty-icon"><span class=\'icon\' data-lucide=\'file-text\'></span></div>
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
    if (window.PharmaUI) window.PharmaUI.errorState(container, { message: `Failed to load documents: ${e.message}`, onRetry: () => qmsDocLoadList(filters) });
    else container.innerHTML = `<div class="qms-empty"><p>Failed to load documents: ${e.message}</p></div>`;
  }
}

// ── Create wizard ───────────────────────────────────────────────────────────

// `prefill` is optional (Phase C, ALD-001 orchestrator rule) — existing
// callers (sidebar "+ New Document", Home Dashboard's "New SOP" quick
// action) call this with no arguments and are unaffected. Project
// Workspace's DQ/FAT/SAT tab passes { doc_type, project_id } so the new
// document is pre-typed and tagged to the active project — this module
// still does all the actual work (modal, validation, POST), Project
// Workspace just supplies a starting point.
// Document Control redesign (spec §4/§6): the create step is where the
// author picks the CONTROLLED SOP TEMPLATE (index + controlled headings/
// sub-headings) — creating the document immediately creates its 0.1 Draft
// (qms_document_database.create_initial_version, server-side, automatic).
// Workflow initiation happens later, only once Self-Check + Final Author
// Version are complete — see qmsDocRenderWorkflowTab.
async function qmsDocOpenNew(prefill) {
  if (window.PharmaAuth && !window.PharmaAuth.requireCompanyContext()) return;
  await qmsLoadMeta();
  const meta = window.QMS_META || { document_types: [] };
  const presetType = (prefill && prefill.doc_type) || "SOP";
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";
  overlay.id = "qms-doc-new-modal";
  overlay.dataset.prefillProjectId = (prefill && prefill.project_id) || "";
  overlay.innerHTML = `
    <div class="modal open qms-modal-lg">
      <div class="modal-header">
        <h2>Create Document</h2>
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
            <select id="qms-new-doc-type" onchange="qmsDocRefreshTemplateOptions()">${qmsOptions(meta.document_types, presetType)}</select>
          </div>
          <div class="form-field">
            <label>Controlled SOP Template</label>
            <select id="qms-new-doc-template"><option value="">Loading templates…</option></select>
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
        <p style="font-size:11.5px;color:var(--text-muted);margin-top:10px">
          Creating the document creates its first Draft version (0.1) automatically. The template's
          controlled headings/sub-headings cannot be removed, renamed, or reordered by AI Assist.
        </p>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="document.getElementById('qms-doc-new-modal').remove()">Cancel</button>
        <button class="btn-primary" id="qms-doc-create-btn" onclick="qmsDocCreate()">Create Document</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  qmsDocRefreshTemplateOptions();
}
window.qmsDocOpenNew = qmsDocOpenNew;

async function qmsDocRefreshTemplateOptions() {
  const typeSel = document.getElementById("qms-new-doc-type");
  const tplSel = document.getElementById("qms-new-doc-template");
  if (!typeSel || !tplSel) return;
  tplSel.innerHTML = `<option value="">Loading templates…</option>`;
  try {
    const templates = await qmsFetch(`/qms/documents/templates?doc_type=${encodeURIComponent(typeSel.value)}`);
    tplSel.innerHTML = templates.length
      ? `<option value="">No template (free-form)</option>` +
        templates.map(t => `<option value="${t.id}">${t.name}</option>`).join("")
      : `<option value="">No controlled template defined for ${typeSel.value} yet</option>`;
  } catch (e) {
    tplSel.innerHTML = `<option value="">Failed to load templates</option>`;
  }
}
window.qmsDocRefreshTemplateOptions = qmsDocRefreshTemplateOptions;

async function qmsDocCreate() {
  const title = document.getElementById("qms-new-doc-title").value.trim();
  if (!title) { qmsToast("Title is required"); return; }
  const btn = document.getElementById("qms-doc-create-btn");
  if (btn.disabled) return;
  btn.disabled = true;
  const templateId = document.getElementById("qms-new-doc-template").value;
  const data = {
    title,
    doc_type: document.getElementById("qms-new-doc-type").value,
    department: document.getElementById("qms-new-doc-dept").value.trim(),
    category: document.getElementById("qms-new-doc-category").value.trim(),
    owner: document.getElementById("qms-new-doc-owner").value.trim(),
  };
  if (templateId) data.template_id = Number(templateId);
  // Optional project tag set by qmsDocOpenNew's prefill (Phase C) — absent
  // for every pre-existing caller, so their payload is unchanged.
  const modalEl = document.getElementById("qms-doc-new-modal");
  const prefillProjectId = modalEl && modalEl.dataset.prefillProjectId;
  if (prefillProjectId) data.project_id = Number(prefillProjectId);
  try {
    const doc = await qmsPostJSON("/qms/documents", data);
    document.getElementById("qms-doc-new-modal").remove();
    qmsToast(`Created ${doc.doc_number}`);
    qmsDocOpenDetail(doc.id);
  } catch (e) {
    qmsToast("Failed to create document: " + e.message);
    btn.disabled = false;
  }
}
window.qmsDocCreate = qmsDocCreate;

// ── New SOP wizard (scope-locked: SOP only, two creation methods) ───────────
// Document Control redesign, SOP workflow correction: the general-purpose
// qmsDocOpenNew() above still exists for Project Workspace's DQ/FAT/SAT tab
// (prefilled, non-SOP doc_type — that Validation Suite integration is out of
// scope for this change and must keep working exactly as before). Every
// no-prefill "create a document" entry point in the product, however, only
// ever produced an SOP with an unrelated 12-option type dropdown attached —
// this replaces those entry points with a minimal, SOP-only flow: Title +
// Creation Method (Create from Controlled Template | AI-Assisted SOP
// Creation), with an Equipment/Knowledge Base picker only when AI-Assisted
// is selected. Both methods create the SOP through the existing
// create_document()/template_id path — no new lifecycle, no new numbering.
async function qmsDocOpenNewSOP() {
  if (window.PharmaAuth && !window.PharmaAuth.requireCompanyContext()) return;
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";
  overlay.id = "qms-doc-new-sop-modal";
  overlay.innerHTML = `
    <div class="modal open">
      <div class="modal-header">
        <h2>Create New SOP</h2>
        <button class="modal-close" onclick="document.getElementById('qms-doc-new-sop-modal').remove()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-field">
          <label>Title</label>
          <input type="text" id="qms-new-sop-title" placeholder="e.g. Cleaning of Tablet Compression Machine" />
        </div>
        <div class="form-field" style="margin-top:14px">
          <label>Creation Method</label>
          <div style="display:flex;flex-direction:column;gap:10px;margin-top:6px">
            <label style="display:flex;align-items:flex-start;gap:8px;font-weight:400;cursor:pointer">
              <input type="radio" name="qms-sop-method" value="template" checked onchange="qmsDocSopMethodChanged()" style="margin-top:3px" />
              <span><strong>Create from Controlled Template</strong><br/>
                <span style="font-size:11.5px;color:var(--text-muted)">Download the approved SOP template (.docx) and prepare it manually.</span></span>
            </label>
            <label style="display:flex;align-items:flex-start;gap:8px;font-weight:400;cursor:pointer">
              <input type="radio" name="qms-sop-method" value="ai" onchange="qmsDocSopMethodChanged()" style="margin-top:3px" />
              <span><strong>AI-Assisted SOP Creation</strong><br/>
                <span style="font-size:11.5px;color:var(--text-muted)">PharmaGPT drafts an initial SOP using controlled Knowledge Base references for the equipment you select. You review and edit before submitting for review — nothing is auto-approved.</span></span>
            </label>
          </div>
        </div>
        <div class="form-field" id="qms-sop-equipment-field" style="margin-top:14px;display:none">
          <label>Equipment / Knowledge Base</label>
          <select id="qms-new-sop-equipment"><option value="">Loading equipment…</option></select>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="document.getElementById('qms-doc-new-sop-modal').remove()">Cancel</button>
        <button class="btn-primary" id="qms-doc-create-sop-btn" onclick="qmsDocCreateSOP()">Create SOP</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  qmsDocLoadEquipmentOptions();
}
window.qmsDocOpenNewSOP = qmsDocOpenNewSOP;

function qmsDocSopMethodChanged() {
  const checked = document.querySelector('input[name="qms-sop-method"]:checked');
  const field = document.getElementById("qms-sop-equipment-field");
  if (checked && field) field.style.display = checked.value === "ai" ? "" : "none";
}
window.qmsDocSopMethodChanged = qmsDocSopMethodChanged;

async function qmsDocLoadEquipmentOptions() {
  const sel = document.getElementById("qms-new-sop-equipment");
  if (!sel) return;
  try {
    const equipment = await qmsFetch("/equipment");
    sel.innerHTML = equipment.length
      ? `<option value="">Select equipment…</option>` +
        equipment.map(e => `<option value="${e.id}">${e.name}${e.equipment_code ? " (" + e.equipment_code + ")" : ""}</option>`).join("")
      : `<option value="">No equipment records found</option>`;
  } catch (e) {
    sel.innerHTML = `<option value="">Failed to load equipment</option>`;
  }
}

async function qmsDocCreateSOP() {
  const title = document.getElementById("qms-new-sop-title").value.trim();
  if (!title) { qmsToast("Title is required"); return; }
  const methodEl = document.querySelector('input[name="qms-sop-method"]:checked');
  const method = methodEl ? methodEl.value : "template";
  const equipmentSel = document.getElementById("qms-new-sop-equipment");
  const equipmentId = equipmentSel ? equipmentSel.value : "";
  const btn = document.getElementById("qms-doc-create-sop-btn");
  if (btn.disabled) return;
  btn.disabled = true;
  try {
    const templates = await qmsFetch(`/qms/documents/templates?doc_type=SOP`);
    const templateId = templates.length ? templates[0].id : null;
    const data = { title, doc_type: "SOP" };
    if (templateId) data.template_id = templateId;
    const doc = await qmsPostJSON("/qms/documents", data);
    document.getElementById("qms-doc-new-sop-modal").remove();
    qmsToast(`Created ${doc.doc_number}`);
    if (method === "template") {
      if (templateId) qmsDocDownloadTemplateDocx(templateId);
      else qmsToast("No controlled SOP template is defined yet — the document was created without one.");
    }
    await qmsDocOpenDetail(doc.id);
    if (method === "ai" && equipmentId) {
      await qmsDocSwitchTab("content");
      qmsDocGenerateDraft(doc.id, { equipment_id: Number(equipmentId) });
    }
  } catch (e) {
    qmsToast("Failed to create SOP: " + e.message);
    btn.disabled = false;
  }
}
window.qmsDocCreateSOP = qmsDocCreateSOP;

function qmsDocDownloadTemplateDocx(templateId) {
  const a = document.createElement("a");
  a.href = `/qms/documents/templates/${templateId}/download`;
  a.download = "";
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
}
window.qmsDocDownloadTemplateDocx = qmsDocDownloadTemplateDocx;

// ── Detail view ─────────────────────────────────────────────────────────────

async function qmsDocOpenDetail(id) {
  qmsDocCurrentId = id;
  qmsDocActiveTab = "overview";
  const body = document.getElementById("qms-documents-body");
  body.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading document…</div>`;
  try {
    const doc = await qmsFetch(`/qms/documents/${id}`);
    if (window.PharmaRecent) window.PharmaRecent.recordOpened("documents", doc.id, doc.title, doc.doc_number || "");
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
          ${["overview", "workflow", "content", "versions", "training", "distribution", "attachments", "comments", "audit", "approval"]
            .map(t => `<button class="qms-tab ${t === qmsDocActiveTab ? "active" : ""}" onclick="qmsDocSwitchTab('${t}')">${qmsDocTabLabel(t)}</button>`).join("")}
        </div>
        <div id="qms-doc-tab-body"></div>
      </div>
    `;
    qmsDocRenderTab(doc);
  } catch (e) {
    if (window.PharmaUI) window.PharmaUI.errorState(body, { message: `Failed to load document: ${e.message}`, onRetry: () => qmsDocOpenDetail(id) });
    else body.innerHTML = `<div class="qms-empty"><p>Failed to load document: ${e.message}</p></div>`;
  }
}
window.qmsDocOpenDetail = qmsDocOpenDetail;

function qmsDocTabLabel(t) {
  return {
    overview: "Overview", workflow: "Workflow", content: "Content / AI Draft", versions: "Version History",
    training: "Training", distribution: "Distribution", attachments: "Attachments",
    comments: "Comments", audit: "Audit Trail", approval: "Approval",
  }[t] || t;
}

async function qmsDocSwitchTab(tab) {
  qmsDocActiveTab = tab;
  document.querySelectorAll("#qms-doc-tabs .qms-tab").forEach(b => b.classList.remove("active"));
  const idx = ["overview", "workflow", "content", "versions", "training", "distribution", "attachments", "comments", "audit", "approval"].indexOf(tab);
  const btns = document.querySelectorAll("#qms-doc-tabs .qms-tab");
  if (btns[idx]) btns[idx].classList.add("active");
  const doc = await qmsFetch(`/qms/documents/${qmsDocCurrentId}`);
  qmsDocRenderTab(doc);
}
window.qmsDocSwitchTab = qmsDocSwitchTab;

// Approver Pool name selector (static/js/user_picker.js's selectHTML) — used
// by the Configure Approver Pool modal (see qmsDocOpenApproverPoolSettings
// below) so a company_admin picks Reviewer/Department Head/Quality Head/
// Plant Head by name; the Supabase user id is resolved and stored
// internally, never shown or typed.
let qmsDocApproverDirectory = null;

function qmsDocRenderTab(doc) {
  const el = document.getElementById("qms-doc-tab-body");
  const id = doc.id;

  if (qmsDocActiveTab === "overview") {
    el.innerHTML = `
      <div class="qms-section-card">
        <h3>Document Control Information</h3>
        <div class="form-grid">
          <div class="form-field"><label>Document Number</label><input type="text" value="${doc.doc_number || "—"}" disabled /></div>
          <div class="form-field"><label>Title</label><input type="text" value="${doc.title || ""}" disabled /></div>
          <div class="form-field"><label>Version</label><input type="text" value="${doc.version}" disabled title="System-controlled — see Version History tab" /></div>
          <div class="form-field"><label>Status</label><input type="text" value="${doc.status}" disabled /></div>
          <div class="form-field"><label>Department</label><input type="text" value="${doc.department || "—"}" disabled /></div>
          <div class="form-field"><label>Effective Date</label><input type="text" value="${doc.effective_date || "—"}" disabled title="Assigned/confirmed only at Quality Release" /></div>
          <div class="form-field"><label>Prepared By</label><input type="text" value="${doc.prepared_by || "—"}" disabled title="Automatically derived from the Author who created this document" /></div>
          <div class="form-field"><label>Reviewed By</label><input type="text" value="${doc.reviewed_by || "—"}" disabled title="Automatically populated when Review is accepted" /></div>
          <div class="form-field"><label>Approved By</label><input type="text" value="${doc.approved_by || "—"}" disabled title="Automatically populated when Approval quorum is achieved" /></div>
          <div class="form-field"><label>Review Date</label><input type="text" value="${doc.review_date || "—"}" disabled title="Set automatically when Review is accepted" /></div>
          <div class="form-field"><label>Expiry Date</label><input type="date" id="qms-ov-expiry" value="${doc.expiry_date || ""}" /></div>
          <div class="form-field"><label>Owner</label><input type="text" id="qms-ov-owner" value="${doc.owner || ""}" /></div>
        </div>
        <p style="font-size:11.5px;color:var(--text-muted);margin-top:2px">
          Document Number, Version, Status, Department, Effective Date, Prepared By, Reviewed By, and Approved By
          are system-controlled and cannot be edited here — see the <strong>Workflow</strong> tab for the current
          lifecycle stage and required actions.
        </p>
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
          ${doc.template_id
            ? "Generates content under this document's Controlled SOP Template — the controlled headings/sub-headings are preserved; missing site-specific detail is flagged for you to complete."
            : `Generates complete ${doc.doc_type} content (Purpose, Scope, Responsibilities, Procedure, Acceptance Criteria, References) — no controlled template was selected at creation.`}
        </p>
        <div class="qms-form-actions" style="justify-content:flex-start;margin-top:0;margin-bottom:14px">
          <button class="btn-primary" id="qms-doc-generate-btn" onclick="qmsDocGenerateDraft(${id})"><span class=\'icon\' data-lucide=\'sparkles\'></span> Generate Draft with AI</button>
          <button class="btn-secondary" id="qms-doc-review-btn" onclick="qmsDocRunReview(${id})">Run Regulatory Compliance Review</button>
        </div>
        <div id="qms-doc-review-result"></div>
        <div id="qms-doc-structure-warning"></div>
        <textarea id="qms-doc-content-editor" style="width:100%;min-height:400px;font-family:monospace;font-size:12px;padding:14px;border:1px solid var(--border);border-radius:6px" placeholder="Document content (markdown)…">${doc.content || ""}</textarea>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsDocSaveContent(${id})">Save Content</button>
        </div>
      </div>
    `;
    if (doc.ai_review_data && doc.ai_review_data.overall_score) {
      qmsDocRenderReview(doc.ai_review_data);
    }
  } else if (qmsDocActiveTab === "workflow") {
    qmsDocRenderWorkflowTab(id, doc);
  } else if (qmsDocActiveTab === "versions") {
    qmsDocRenderVersions(id, doc);
  } else if (qmsDocActiveTab === "training") {
    qmsDocRenderTraining(id);
  } else if (qmsDocActiveTab === "distribution") {
    qmsDocRenderDistribution(id);
  } else if (qmsDocActiveTab === "attachments") {
    el.innerHTML = `
      <div class="qms-section-card" style="margin-bottom:14px">
        <p style="font-size:12.5px;color:var(--text-muted);margin:0">
          <strong>Supporting records only</strong> — specifications, risk assessments, validation reports,
          reference material. This is <strong>not</strong> the controlled document content. Use
          <strong>Upload Final Author Version</strong> on the Workflow tab for the content that Review and
          Approval act on.
        </p>
      </div>
      <div id="qms-attachments-document-${id}"></div>`;
    qmsRenderAttachments(`qms-attachments-document-${id}`, "document", id);
  } else if (qmsDocActiveTab === "comments") {
    el.innerHTML = `<div id="qms-comments-document-${id}"></div>`;
    qmsRenderComments(`qms-comments-document-${id}`, "document", id);
  } else if (qmsDocActiveTab === "audit") {
    el.innerHTML = `<div id="qms-audit-document-${id}"></div>`;
    qmsRenderAuditTrail(`qms-audit-document-${id}`, "document", id);
  } else if (qmsDocActiveTab === "approval") {
    qmsDocRenderApprovalTrailReadOnly(id);
  }
}

// Document Control redesign: Review Accept/Reject and Approval votes are now
// decided exclusively from the Workflow tab (state-machine-enforced, one
// action per current step). This tab is read-only history — showing the
// free-form legacy action dropdown here would let a user attempt an action
// that bypasses the engine and gets rejected server-side with a confusing
// 409, or (for a genuinely legal legacy action) duplicate the Workflow tab.
async function qmsDocRenderApprovalTrailReadOnly(id) {
  const el = document.getElementById("qms-doc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading approval trail…</div>`;
  try {
    const entries = await qmsFetch(`/qms/document/${id}/approval`);
    el.innerHTML = `
      <div class="qms-section-card" style="margin-bottom:14px">
        <p style="font-size:12px;color:var(--text-muted);margin:0">
          Review Accept/Reject and Approval votes are decided from the <strong>Workflow</strong> tab.
          This is a read-only record of those decisions; see <strong>Audit Trail</strong> for the complete
          lifecycle history.
        </p>
      </div>
      ${entries.length ? entries.map(a => `
        <div class="qms-panel-item">
          <div>
            <span class="qms-audit-action">${a.action}</span>
            <div class="qms-panel-item-meta">${a.performed_by || ""}${a.role ? ` (${a.role})` : ""} · ${a.created_at}</div>
            ${a.comments ? `<div>${a.comments}</div>` : ""}
          </div>
        </div>`).join("") : `<div class="qms-empty"><p>No approval actions recorded yet.</p></div>`}
    `;
  } catch (e) {
    el.innerHTML = `<div class="qms-empty"><p>Failed to load approval trail: ${e.message}</p></div>`;
  }
}

// ── Workflow tab (Document Control redesign): state-aware Author Workspace /
// Review & Approval / Quality Release panel — replaces the raw "Start
// Workflow" generic panel as the primary Document Control UI. Only once a
// workflow instance actually exists does this delegate to the shared
// renderWorkflowPanel (workflow_panel.js) for the live step-decision UI. ───

async function qmsDocRenderWorkflowTab(id, doc) {
  const el = document.getElementById("qms-doc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading workflow…</div>`;
  let version;
  try {
    version = await qmsFetch(`/qms/documents/${id}/versions/current`);
  } catch (e) {
    el.innerHTML = `<div class="qms-empty"><p>Failed to load current version: ${e.message}</p></div>`;
    return;
  }

  if (version.status === "draft") {
    await qmsDocRenderDraftStepper(id, doc, version);
  } else if (version.status === "under_review" || version.status === "pending_approval") {
    await qmsDocRenderReviewApprovalPanel(id, doc, version);
  } else if (version.status === "approved") {
    await qmsDocRenderReleasePanel(id, doc, version);
  } else if (version.status === "effective") {
    qmsDocRenderEffectivePanel(id, doc, version);
  } else {
    // review_rejected / approval_rejected / superseded should never be the
    // CURRENT version (a rejection always forks a fresh Draft current
    // version) — rendered read-only as a defensive fallback only.
    qmsDocRenderImmutableVersionPanel(id, doc, version);
  }
}

async function qmsDocRenderDraftStepper(id, doc, version) {
  const el = document.getElementById("qms-doc-tab-body");
  const selfCheckDone = !!version.self_check_completed_at;
  const finalUploaded = !!version.source_attachment_id;
  let finalFile = null;
  if (finalUploaded) {
    try {
      const atts = await qmsFetch(`/qms/document/${id}/attachments`);
      finalFile = atts.find(a => a.id === version.source_attachment_id) || null;
    } catch (e) { /* non-fatal — upload confirmation still shown without file details */ }
  }
  // SOP workflow correction (§2/§3): the Author assigns the COMPLETE
  // review/approval chain before submission — fetched here (not just on
  // demand) so "chainComplete" can gate Submit for Review alongside the
  // pre-existing Self-Check/Final Version gates.
  let chain = { reviewer: null, department_head: null, quality_head: null, plant_head: null };
  try { chain = await qmsFetch(`/qms/documents/${id}/assign-chain`); } catch (e) { /* leave defaults — form still renders */ }
  const chainComplete = !!(chain.reviewer && chain.department_head && chain.quality_head);
  const readyToSubmit = selfCheckDone && finalUploaded && chainComplete;
  const missing = [
    !selfCheckDone && "Author Self-Check",
    !finalUploaded && "Final Author Version upload",
    !chainComplete && "Review & Approval Chain assignment",
  ].filter(Boolean);

  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Draft ${version.version_number} — Author Workspace</h3>
      <p style="font-size:12px;color:var(--text-muted);margin-top:0">Complete these steps in order, then Submit for Review.</p>
    </div>
    <div class="qms-workflow-stepper">
      <div class="qms-stat-card">
        <strong>1. Download Draft (DOCX)</strong>
        <p style="font-size:11.5px;color:var(--text-muted);margin:4px 0">Downloads the current draft — including AI-generated content and the controlled template structure — as a Word document.</p>
        <div class="qms-form-actions" style="margin-top:6px">
          <button class="btn-secondary" onclick="qmsDocExportDocx(${id})">Download</button>
        </div>
      </div>
      <div class="qms-stat-card">
        <strong>2. Content / AI Assist</strong>
        <div class="qms-form-actions" style="margin-top:6px">
          <button class="btn-secondary" onclick="qmsDocSwitchTab('content')">Go to Content Tab</button>
        </div>
      </div>
      <div class="qms-stat-card ${selfCheckDone ? "success" : "info"}">
        <strong>3. Author Self-Check${selfCheckDone ? " — Complete" : ""}</strong>
        ${selfCheckDone
          ? `<div class="qms-panel-item-meta">Completed ${version.self_check_completed_at}</div>`
          : `<p style="font-size:11.5px;color:var(--text-muted);margin:4px 0">Confirms the content has been reviewed against the controlled headings and is accurate and complete.</p>
             <div class="qms-form-actions"><button class="btn-primary" onclick="qmsDocRecordSelfCheck(${id})">Complete Author Self-Check</button></div>`}
      </div>
      <div class="qms-stat-card ${finalUploaded ? "success" : "info"}">
        <strong>4. Upload Final Author Version${finalUploaded ? " — Uploaded" : ""}</strong>
        ${finalUploaded ? `<div class="qms-panel-item-meta">${finalFile ? (finalFile.original_name || finalFile.filename) : "File"}${finalFile && finalFile.uploaded_by ? " · uploaded by " + finalFile.uploaded_by : ""}${finalFile && finalFile.created_at ? " · " + finalFile.created_at : ""}</div>` : ""}
        <p style="font-size:11.5px;color:var(--text-muted);margin:4px 0">Edit the file locally, then upload it here — it becomes the controlled content for this version. This is separate from Attachments.</p>
        <div class="form-field"><input type="file" id="qms-final-version-file-${id}" /></div>
        <div class="qms-form-actions" style="margin-top:6px">
          <button class="btn-secondary" onclick="qmsDocUploadFinalVersion(${id})">${finalUploaded ? "Re-upload" : "Upload"} Final Author Version</button>
        </div>
      </div>
      <div class="qms-stat-card ${chainComplete ? "success" : "info"}" id="qms-chain-card-${id}">
        <strong>5. Assign Review &amp; Approval Chain${chainComplete ? " — Assigned" : ""}</strong>
        <p style="font-size:11.5px;color:var(--text-muted);margin:4px 0">You assign the complete chain now — Reviewer, Department Head, and Quality Head are required; Plant Head is optional. Once submitted, this cannot be changed.</p>
        <div id="qms-chain-form-${id}"><div class="qms-loading"><div class="qms-spinner"></div> Loading users…</div></div>
      </div>
      <div class="qms-stat-card ${readyToSubmit ? "info" : ""}">
        <strong>6. Submit for Review</strong>
        <p style="font-size:11.5px;color:var(--text-muted);margin:4px 0">
          ${readyToSubmit ? "All gates complete." : `Blocked — needs: ${missing.join(", ")}.`}
        </p>
        <div class="qms-form-actions">
          <button class="btn-primary" ${readyToSubmit ? "" : "disabled"} onclick="qmsDocSubmitForReview(${id})">Submit for Review</button>
        </div>
      </div>
    </div>
  `;
  qmsDocRenderChainForm(id, chain);
}

// SOP workflow correction (§3): Reviewer/Department Head/Quality Head/Plant
// Head selectors, populated from the tenant's existing user directory
// (window.UserPicker, static/js/user_picker.js) — same designation-based
// soft filter as the Workflow tab's own picker (workflow_panel.js's
// WF_POOL_ROLE_DESIGNATION/wfPanelFilteredDirectory), reused here rather
// than re-implemented. Prefilled with the current selection so the Author
// can change it freely up until Submit for Review actually locks it
// (POST .../assign-chain 409s server-side once the version leaves Draft —
// see qms_document_database.set_review_chain).
async function qmsDocRenderChainForm(id, chain) {
  const el = document.getElementById(`qms-chain-form-${id}`);
  if (!el) return;
  const directory = (window.UserPicker && (await window.UserPicker.loadDirectory())) || [];
  const roles = [
    { role: "reviewer", label: "Reviewer", optional: false },
    { role: "department_head", label: "Department Head", optional: false },
    { role: "quality_head", label: "Quality Head", optional: false },
    { role: "plant_head", label: "Plant Head", optional: true },
  ];
  el.innerHTML = roles.map(r => {
    const current = chain[r.role];
    const options = window.wfPanelFilteredDirectory ? window.wfPanelFilteredDirectory(directory, r.role) : directory;
    return `
      <div class="form-field" style="max-width:320px;margin-top:8px">
        <label>${r.label}${r.optional ? " (Optional)" : ""}</label>
        ${window.UserPicker
          ? window.UserPicker.selectHTML(`qms-chain-select-${id}-${r.role}`, options, current ? current.user_id : "")
          : `<input type="text" id="qms-chain-select-${id}-${r.role}" placeholder="Select…" />`}
      </div>
    `;
  }).join("") + `
    <div class="qms-form-actions" style="margin-top:8px">
      <button class="btn-secondary" onclick="qmsDocSaveReviewChain(${id})">Save Assignment</button>
    </div>
  `;
}
window.qmsDocRenderChainForm = qmsDocRenderChainForm;

async function qmsDocSaveReviewChain(id) {
  const roles = ["reviewer", "department_head", "quality_head", "plant_head"];
  const data = {};
  const missing = [];
  for (const role of roles) {
    const sel = document.getElementById(`qms-chain-select-${id}-${role}`);
    const userId = sel ? sel.value : "";
    const opt = sel && sel.tagName === "SELECT" ? sel.options[sel.selectedIndex] : null;
    const name = opt ? opt.textContent.split(" (")[0] : "";
    data[`${role}_user_id`] = userId;
    data[`${role}_name`] = userId ? name : "";
    if (!userId && role !== "plant_head") missing.push(role);
  }
  if (missing.length) { qmsToast("Reviewer, Department Head, and Quality Head are required"); return; }
  try {
    await qmsPostJSON(`/qms/documents/${id}/assign-chain`, data);
    qmsToast("Review & Approval Chain assigned");
    qmsDocSwitchTab("workflow");
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDocSaveReviewChain = qmsDocSaveReviewChain;

async function qmsDocRecordSelfCheck(id) {
  const confirmed = confirm(
    "Confirm Author Self-Check: the content has been reviewed against the controlled headings/" +
    "sub-headings, is accurate and complete, and is ready for Final Author Version upload."
  );
  if (!confirmed) return;
  try {
    await qmsPostJSON(`/qms/documents/${id}/self-check`, {});
    qmsToast("Author Self-Check recorded");
    qmsDocSwitchTab("workflow");
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDocRecordSelfCheck = qmsDocRecordSelfCheck;

async function qmsDocUploadFinalVersion(id) {
  const input = document.getElementById(`qms-final-version-file-${id}`);
  if (!input || !input.files.length) { qmsToast("Choose a file first"); return; }
  const fd = new FormData();
  fd.append("file", input.files[0]);
  try {
    const res = await fetch(`/qms/documents/${id}/versions/upload`, { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Upload failed (${res.status})`);
    qmsToast("Final Author Version uploaded");
    qmsDocSwitchTab("workflow");
  } catch (e) {
    qmsToast("Upload failed: " + e.message);
  }
}
window.qmsDocUploadFinalVersion = qmsDocUploadFinalVersion;

async function qmsDocSubmitForReview(id) {
  try {
    await qmsPostJSON(`/qms/documents/${id}/workflow/start`, {});
    qmsToast("Submitted for Review");
    qmsDocSwitchTab("workflow");
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDocSubmitForReview = qmsDocSubmitForReview;

async function qmsDocRenderReviewApprovalPanel(id, doc, version) {
  const el = document.getElementById("qms-doc-tab-body");
  // SOP workflow correction (§7/§8/§9/§11): the Reviewer/Department Head/
  // Quality Head/Plant Head's PRIMARY surface is the controlled SOP itself —
  // a read-only PDF (GET .../review-pdf, an <iframe> so it renders in-app,
  // no external Word download needed) with an UNDER REVIEW/PENDING
  // APPROVAL/APPROVED watermark on every page while not yet Effective (see
  // services/qms_document_service.py::generate_review_pdf). The generic
  // Workflow Panel below it (unchanged, shared with CAPA/Change Control)
  // still owns Comments + Accept/Request Changes/Approve/Reject — this
  // block only adds the document itself above those existing controls.
  el.innerHTML = `
    <div class="qms-section-card" style="margin-bottom:14px">
      <h3>SOP Review — ${doc.doc_number || ""}</h3>
      <div class="qms-detail-meta">
        <span>Title: ${doc.title || ""}</span>
        <span>Version: ${version.version_number}</span>
        <span>${qmsBadge((QMS_VERSION_STATUS_LABEL[version.status] || version.status || "").toString().toUpperCase())}</span>
      </div>
    </div>
    <div class="qms-section-card" style="margin-bottom:14px;padding:0;overflow:hidden">
      <iframe src="/qms/documents/${id}/review-pdf" title="Controlled SOP review (read-only)"
              style="width:100%;height:70vh;border:none;display:block"></iframe>
    </div>
    <div id="qms-workflow-document-${id}"></div>
  `;
  await renderWorkflowPanel(`qms-workflow-document-${id}`, "document", "/qms/documents", id);
}

async function qmsDocRenderReleasePanel(id, doc, version) {
  const el = document.getElementById("qms-doc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading training gate…</div>`;
  let gate;
  try {
    gate = await qmsFetch(`/qms/documents/${id}/training/gate`);
  } catch (e) {
    el.innerHTML = `<div class="qms-empty"><p>Failed to load training gate: ${e.message}</p></div>`;
    return;
  }
  const user = (window.PharmaAuth && window.PharmaAuth.getUser()) || {};
  const canRelease = user.role === "company_admin" || user.role === "reviewer_qa";
  const pct = gate.completion_pct == null ? "—" : `${gate.completion_pct.toFixed(1)}%`;
  const today = new Date().toISOString().slice(0, 10);

  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Version ${version.version_number} — Approved, Awaiting Quality Release</h3>
      <p style="font-size:12px;color:var(--text-muted)">
        Quorum Approval is complete. Training completion must reach ${gate.threshold_pct.toFixed(0)}%
        before this document can be released as Effective by the Quality Coordinator.
      </p>
      <div class="qms-stats-grid">
        <div class="qms-stat-card ${gate.cleared ? "success" : "critical"}">
          <div class="qms-stat-value">${pct}</div>
          <div class="qms-stat-label">Training Completion: minimum 90% required for Quality Release (${gate.trainee_count} trainee${gate.trainee_count === 1 ? "" : "s"})</div>
        </div>
      </div>
      ${gate.cleared ? "" : `<p style="font-size:12.5px;color:var(--danger,#c0392b)">Blocked — go to the Training tab to record/complete training.</p>`}
      ${canRelease ? `
        <div class="form-field" style="max-width:220px;margin-top:10px">
          <label>Effective Date</label>
          <input type="date" id="qms-release-effective-date-${id}" value="${today}" />
        </div>
        <div class="qms-form-actions">
          <button class="btn-primary" ${gate.cleared ? "" : "disabled"} onclick="qmsDocReleaseEffective(${id})">Quality Release</button>
        </div>`
        : `<p style="font-size:11.5px;color:var(--text-muted)">Only a Quality Coordinator / authorized Quality role can perform Quality Release — the Author cannot make an SOP Effective.</p>`}
    </div>
  `;
}

async function qmsDocReleaseEffective(id) {
  if (!window.PharmaESign) { qmsToast("Electronic Signature dialog failed to load"); return; }
  const dateEl = document.getElementById(`qms-release-effective-date-${id}`);
  const effective_date = dateEl ? dateEl.value : "";
  // 21 CFR Part 11 / EU GMP Annex 11: Quality Release is a GMP decision and
  // requires a fresh Electronic Signature.
  window.PharmaESign.open({
    meaning: "Released",
    onConfirm: async ({ password, meaning, reason }) => {
      try {
        await qmsPostJSON(`/qms/documents/${id}/release`, { password, meaning, reason, effective_date });
        qmsToast("Quality Release complete — document is now Effective");
        qmsDocSwitchTab("workflow");
      } catch (e) {
        qmsToast("Quality Release failed: " + e.message);
      }
    },
  });
}
window.qmsDocReleaseEffective = qmsDocReleaseEffective;

function qmsDocRenderEffectivePanel(id, doc, version) {
  const el = document.getElementById("qms-doc-tab-body");
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Version ${version.version_number} — Effective</h3>
      <div class="qms-panel-item-meta">Effective ${version.effective_date || "—"}</div>
      <p style="font-size:12px;color:var(--text-muted)">This version is the controlled, released document. To make a change, start a new revision cycle.</p>
      <div class="qms-form-actions">
        <button class="btn-primary" onclick="qmsDocStartRevision(${id})">Start New Revision</button>
      </div>
    </div>
  `;
}

async function qmsDocStartRevision(id) {
  try {
    await qmsPostJSON(`/qms/documents/${id}/versions/start-revision`, {});
    qmsToast("New revision started");
    qmsDocSwitchTab("workflow");
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDocStartRevision = qmsDocStartRevision;

function qmsDocRenderImmutableVersionPanel(id, doc, version) {
  const el = document.getElementById("qms-doc-tab-body");
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Version ${version.version_number} — ${QMS_VERSION_STATUS_LABEL[version.status] || version.status}</h3>
      <p style="font-size:12px;color:var(--text-muted)">This version is immutable. See the Version History tab for the full timeline.</p>
    </div>
  `;
}

async function qmsDocSaveOverview(id) {
  // Version/Status/Effective Date/Review Date are system-controlled (spec
  // §8/§9/§22) — not sent from this form. The backend independently drops
  // effective_date/review_date if a stale client build still sends them.
  const data = {
    expiry_date: document.getElementById("qms-ov-expiry").value,
    owner: document.getElementById("qms-ov-owner").value.trim(),
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

function qmsDocGenerateDraft(id, extraBody) {
  const editor = document.getElementById("qms-doc-content-editor");
  const reviewBtn = document.getElementById("qms-doc-review-btn");
  const genBtn = document.getElementById("qms-doc-generate-btn");
  const warnEl = document.getElementById("qms-doc-structure-warning");
  if (warnEl) warnEl.innerHTML = "";
  editor.value = "";
  editor.disabled = true;
  if (reviewBtn) reviewBtn.disabled = true;
  if (genBtn) genBtn.disabled = true;
  qmsToast("Generating draft…");
  qmsStream(`/qms/documents/${id}/generate`, extraBody || {}, {
    onChunk: chunk => { editor.value += chunk; editor.scrollTop = editor.scrollHeight; },
    onDone: (event) => {
      editor.disabled = false;
      if (reviewBtn) reviewBtn.disabled = false;
      if (genBtn) genBtn.disabled = false;
      qmsToast("Draft generated");
      // Document Control redesign (spec §6): AI Assist must never remove,
      // rename, or reorder controlled headings — validate_template_structure()
      // (services/qms_document_prompt.py) is the deterministic backstop; this
      // surfaces its result so the Author sees a violation immediately
      // instead of only finding it in the audit trail.
      const check = event && event.structure_check;
      if (warnEl && check && !check.valid) {
        warnEl.innerHTML = `
          <div class="qms-section-card" style="border-color:var(--danger,#c0392b);margin-top:12px">
            <h3 style="color:var(--danger,#c0392b)">Controlled Template Structure Violation</h3>
            ${check.missing_headings && check.missing_headings.length ? `<p><strong>Missing controlled heading(s):</strong> ${check.missing_headings.join(", ")}</p>` : ""}
            ${check.out_of_order && check.out_of_order.length ? `<p><strong>Out-of-order heading(s):</strong> ${check.out_of_order.join(", ")}</p>` : ""}
            <p style="font-size:12px;color:var(--text-muted)">Fix the content below before Author Self-Check — the controlled index/headings/sub-headings must be preserved exactly.</p>
          </div>`;
      }
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

// Document Control redesign (spec §3/§21): version creation is entirely
// system-controlled (Self-Check + Final Author Version + Review + Approval +
// Training drive numbering — see services/document_versioning.py). This tab
// is now a READ-ONLY historical timeline — no "Create New Version" /
// "New Version Label" / "Snapshot Current Content" form. Every version row
// except the current Draft is permanently immutable.
const QMS_VERSION_STATUS_LABEL = {
  draft: "Draft", under_review: "Under Review", pending_approval: "Pending Approval",
  approved: "Approved", effective: "Effective", review_rejected: "Review Rejected",
  approval_rejected: "Approval Rejected", superseded: "Superseded",
};

async function qmsDocRenderVersions(id, doc) {
  const el = document.getElementById("qms-doc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading version history…</div>`;
  const versions = (await qmsFetch(`/qms/documents/${id}/versions`)).slice().reverse(); // oldest -> newest
  if (!versions.length) {
    el.innerHTML = `<div class="qms-empty"><p>No version history recorded.</p></div>`;
    return;
  }
  el.innerHTML = `
    <div class="qms-section-card" style="margin-bottom:14px">
      <h3>Version History</h3>
      <p style="font-size:12px;color:var(--text-muted);margin:0">
        Read-only timeline. Version numbers are assigned automatically and never reused; every version
        except the current Draft is permanently immutable.
      </p>
    </div>
    <div class="qms-workflow-stepper">
      ${versions.map(v => qmsVersionTimelineRowHTML(id, doc, v)).join("")}
    </div>
  `;
}

function qmsVersionTimelineRowHTML(id, doc, v) {
  const versionLabel = v.version_number || v.version;
  const isCurrent = doc && doc.current_version_id === v.id;
  const stateClass = v.status === "effective" ? "success"
    : (v.status === "review_rejected" || v.status === "approval_rejected") ? "critical"
    : isCurrent ? "info" : "";
  return `
    <div class="qms-stat-card ${stateClass}" style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong>${versionLabel} — ${QMS_VERSION_STATUS_LABEL[v.status] || v.status || "Draft"}</strong>
        <span class="qms-panel-item-meta">${isCurrent ? "Current — editable by Author" : "Immutable"}</span>
      </div>
      <div class="qms-panel-item-meta">
        Created ${v.created_at || "—"}${v.created_by_user_id ? ` by ${v.created_by_user_id}` : ""}
        ${v.self_check_completed_at ? ` · Self-Check completed ${v.self_check_completed_at}` : ""}
        ${v.effective_date ? ` · Effective ${v.effective_date}` : ""}
      </div>
      ${v.rejection_reason ? `<div class="qms-panel-item-meta">Rejection reason: "${v.rejection_reason}"</div>` : ""}
      <div class="qms-form-actions" style="margin-top:6px">
        <button class="btn-secondary" onclick="qmsDocPrint(${id}, ${v.id})">View / Export</button>
      </div>
    </div>
  `;
}

async function qmsDocRenderTraining(id) {
  const el = document.getElementById("qms-doc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading training records…</div>`;
  const [records, gate] = await Promise.all([
    qmsFetch(`/qms/documents/${id}/training`),
    qmsFetch(`/qms/documents/${id}/training/gate`).catch(() => null),
  ]);
  const gateCard = gate ? `
    <div class="qms-stats-grid" style="margin-bottom:6px">
      <div class="qms-stat-card ${gate.cleared ? "success" : "critical"}">
        <div class="qms-stat-value">Training Completion: ${gate.completion_pct == null ? "—" : gate.completion_pct.toFixed(1) + "%"}</div>
        <div class="qms-stat-label">${gate.trainee_count} trainee${gate.trainee_count === 1 ? "" : "s"} on the current version</div>
      </div>
    </div>
    <p style="font-size:12px;color:${gate.cleared ? "var(--text-muted)" : "var(--danger,#c0392b)"};margin:0 0 14px">
      Minimum ${gate.threshold_pct.toFixed(0)}% training completion required for Quality Release.
    </p>` : "";
  el.innerHTML = `
    ${gateCard}
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
  if (!window.PharmaESign) { qmsToast("Electronic Signature dialog failed to load"); return; }

  // 21 CFR Part 11 / EU GMP Annex 11: completing a training record is a GMP
  // attestation and requires a fresh Electronic Signature — see
  // pharmagpt/services/esignature_service.py.
  window.PharmaESign.open({
    meaning: "Verified",
    onConfirm: async ({ password, meaning, reason }) => {
      await qmsPutJSON(`/qms/documents/training/${trainingId}`, {
        training_status: "Completed", training_date: today, password, meaning, reason,
      });
      qmsDocRenderTraining(docId);
    },
  });
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

// ── Approver Pool settings (Document Control redesign, spec §13) ────────────
// company_admin-only: Department Head + Quality Head (mandatory) and Plant
// Head (optional) — the final Approval step's quorum is auto-derived from
// this pool (routes/qms_documents.py::_effective_quorum_and_pool_approvers),
// scoped by department with a company-wide default (department="").

const QMS_APPROVER_POOL_ROLES = [
  { role: "reviewer", label: "Reviewer" },
  { role: "department_head", label: "Department Head" },
  { role: "quality_head", label: "Quality Head / Designee" },
  { role: "plant_head", label: "Plant Head (Optional)" },
];

async function qmsDocOpenApproverPoolSettings() {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";
  overlay.id = "qms-approver-pool-modal";
  overlay.innerHTML = `
    <div class="modal open qms-modal-lg">
      <div class="modal-header">
        <h2>Configure Approver Pool</h2>
        <button class="modal-close" onclick="document.getElementById('qms-approver-pool-modal').remove()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-field">
          <label>Department (leave blank for the company-wide default pool)</label>
          <input type="text" id="qms-pool-dept" placeholder="e.g. Quality Assurance" oninput="qmsDocLoadApproverPool()" />
        </div>
        <div id="qms-pool-rows"></div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="document.getElementById('qms-approver-pool-modal').remove()">Close</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  await qmsDocLoadApproverPool();
}
window.qmsDocOpenApproverPoolSettings = qmsDocOpenApproverPoolSettings;

async function qmsDocLoadApproverPool() {
  const dept = document.getElementById("qms-pool-dept").value.trim();
  const rowsEl = document.getElementById("qms-pool-rows");
  rowsEl.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading…</div>`;
  const [pool] = await Promise.all([
    qmsFetch(`/qms/documents/approver-pool?department=${encodeURIComponent(dept)}`),
    (async () => { if (!qmsDocApproverDirectory) qmsDocApproverDirectory = await window.UserPicker.loadDirectory(); })(),
  ]);
  const byRole = {};
  pool.forEach(p => { byRole[p.pool_role] = p; });
  // Name-only selector (final correction pass §2): a real <select> of the
  // tenant's users, resolving to user_id internally — the author never
  // sees or enters a Supabase user id or a separate free-text display name.
  rowsEl.innerHTML = QMS_APPROVER_POOL_ROLES.map(r => {
    const current = byRole[r.role];
    return `
      <div class="qms-section-card" style="margin-top:10px">
        <h3 style="margin-top:0">${r.label}</h3>
        ${current ? `<div class="qms-panel-item-meta">Currently: ${current.display_name || current.user_id}</div>` : `<div class="qms-panel-item-meta">Not configured</div>`}
        <div class="form-field" style="max-width:320px">
          <label>Select ${r.label}</label>
          ${window.UserPicker.selectHTML(`qms-pool-select-${r.role}`, qmsDocApproverDirectory || [], current ? current.user_id : "")}
        </div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsDocSaveApproverPoolRole('${r.role}')">Save</button>
        </div>
      </div>
    `;
  }).join("");
}
window.qmsDocLoadApproverPool = qmsDocLoadApproverPool;

async function qmsDocSaveApproverPoolRole(pool_role) {
  const dept = document.getElementById("qms-pool-dept").value.trim();
  const sel = document.getElementById(`qms-pool-select-${pool_role}`);
  const user_id = sel.value;
  if (!user_id) { qmsToast("Please select a person"); return; }
  const entry = (qmsDocApproverDirectory || []).find(e => e.user_id === user_id);
  const display_name = entry ? entry.display_name : "";
  try {
    await qmsPostJSON(`/qms/documents/approver-pool`, { department: dept, pool_role, user_id, display_name });
    qmsToast("Approver pool updated");
    qmsDocLoadApproverPool();
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDocSaveApproverPoolRole = qmsDocSaveApproverPoolRole;

// ── Print / Export ──────────────────────────────────────────────────────────

async function qmsDocPrint(id, versionId) {
  try {
    const url = versionId ? `/qms/documents/${id}/report?version_id=${versionId}` : `/qms/documents/${id}/report`;
    const { markdown, title } = await qmsFetch(url);
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
    // Use the server's Content-Disposition filename (doc number + title,
    // always ends in .docx — routes/qms_documents.py::export_docx) rather
    // than a generic hardcoded name; a blob: URL carries no header info of
    // its own, so this must be parsed out before the blob is created.
    const cd = res.headers.get("content-disposition") || "";
    const match = cd.match(/filename="?([^";]+)"?/);
    const filename = match ? match[1] : `Document_${id}.docx`;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    qmsToast("Export error: " + e.message);
  }
}
window.qmsDocExportDocx = qmsDocExportDocx;
