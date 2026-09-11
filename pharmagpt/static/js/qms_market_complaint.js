/*
 * qms_market_complaint.js — Market Complaint Management module frontend (P0).
 *
 * Renders entirely into <main id="view-qms-market-complaint"><div id="qms-mc-body">.
 * Follows the same structure as qms_capa.js / qms_change_control.js. Reuses
 * workflow_panel.js's renderWorkflowPanel for the Lifecycle tab and
 * qms_common.js's shared Attachments/Comments/Audit Trail panels — no new
 * generic UI framework.
 */

let qmsMcCurrentId = null;
let qmsMcActiveTab = "overview";

function initQMSMarketComplaint() {
  qmsLoadMeta().then(() => qmsMcShowList());
}
window.initQMSMarketComplaint = initQMSMarketComplaint;

// ── List view ───────────────────────────────────────────────────────────────

async function qmsMcShowList(filters = {}) {
  qmsMcCurrentId = null;
  const body = document.getElementById("qms-mc-body");
  body.innerHTML = `
    <div class="qms-page-header">
      <div>
        <h2>Market Complaint Management</h2>
        <p>Complaint intake, triage &amp; risk assessment, QA review, and closure</p>
      </div>
      <div class="qms-header-actions">
        <button class="btn-primary" onclick="qmsMcOpenNew()">+ New Complaint</button>
      </div>
    </div>
    <div class="qms-body">
      <div id="qms-mc-toolbar"></div>
      <div id="qms-mc-list-container"><div class="qms-loading"><div class="qms-spinner"></div> Loading complaints…</div></div>
    </div>
  `;
  renderQMSMcToolbar(filters);
  await qmsMcLoadList(filters);
}
window.qmsMcShowList = qmsMcShowList;

function renderQMSMcToolbar(filters) {
  const meta = window.QMS_META || { market_complaint_statuses: [], market_complaint_severities: [] };
  const el = document.getElementById("qms-mc-toolbar");
  el.innerHTML = `
    <div class="qms-toolbar">
      <input type="text" id="qms-mc-search" placeholder="Search by title, number, or description…" value="${filters.q || ""}" />
      <select id="qms-mc-filter-status">
        <option value="">All Statuses</option>
        ${qmsOptions(meta.market_complaint_statuses, filters.status)}
      </select>
      <select id="qms-mc-filter-severity">
        <option value="">All Severities</option>
        ${qmsOptions(meta.market_complaint_severities, filters.severity)}
      </select>
      <input type="text" id="qms-mc-filter-product" placeholder="Product" value="${filters.product || ""}" style="max-width:160px" />
      <input type="text" id="qms-mc-filter-market" placeholder="Market/Country" value="${filters.market_country || ""}" style="max-width:160px" />
      <button class="btn-secondary" onclick="qmsMcApplyFilters()">Filter</button>
    </div>
  `;
  document.getElementById("qms-mc-search").addEventListener("keydown", e => {
    if (e.key === "Enter") qmsMcApplyFilters();
  });
}

function qmsMcApplyFilters() {
  const filters = {
    q: document.getElementById("qms-mc-search").value.trim(),
    status: document.getElementById("qms-mc-filter-status").value,
    severity: document.getElementById("qms-mc-filter-severity").value,
    product: document.getElementById("qms-mc-filter-product").value.trim(),
    market_country: document.getElementById("qms-mc-filter-market").value.trim(),
  };
  qmsMcLoadList(filters);
}
window.qmsMcApplyFilters = qmsMcApplyFilters;

async function qmsMcLoadList(filters = {}) {
  const container = document.getElementById("qms-mc-list-container");
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.status) params.set("status", filters.status);
  if (filters.severity) params.set("severity", filters.severity);
  if (filters.product) params.set("product", filters.product);
  if (filters.market_country) params.set("market_country", filters.market_country);

  try {
    const complaints = await qmsFetch(`/qms/market-complaints?${params.toString()}`);
    if (!complaints.length) {
      container.innerHTML = `
        <div class="qms-empty">
          <div class="qms-empty-icon"><span class='icon' data-lucide='megaphone'></span></div>
          <h3>No market complaints yet</h3>
          <p>Register your first complaint to begin intake and triage.</p>
        </div>`;
      return;
    }
    container.innerHTML = `
      <table class="qms-table">
        <thead><tr><th>Complaint Number</th><th>Title</th><th>Product</th><th>Market/Country</th><th>Severity</th><th>Status</th></tr></thead>
        <tbody>
          ${complaints.map(c => `
            <tr class="clickable" onclick="qmsMcOpenDetail(${c.id})">
              <td>${c.complaint_number}</td>
              <td>${c.title}</td>
              <td>${c.product || "—"}</td>
              <td>${c.market_country || "—"}</td>
              <td>${qmsBadge(c.severity)}</td>
              <td>${qmsBadge(c.status)}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    if (window.PharmaUI) window.PharmaUI.errorState(container, { message: `Failed to load complaints: ${e.message}`, onRetry: () => qmsMcLoadList(filters) });
    else container.innerHTML = `<div class="qms-empty"><p>Failed to load complaints: ${e.message}</p></div>`;
  }
}

// ── Create wizard (Intake) ────────────────────────────────────────────────────

function qmsMcOpenNew() {
  if (window.PharmaAuth && !window.PharmaAuth.requireCompanyContext()) return;
  const meta = window.QMS_META || {
    market_complaint_received_via: [], market_complaint_complainant_types: [],
    market_complaint_classifications: [], market_complaint_severities: [],
    market_complaint_regulatory_profiles: [],
  };
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";
  overlay.id = "qms-mc-new-modal";
  overlay.innerHTML = `
    <div class="modal open qms-modal-lg">
      <div class="modal-header">
        <h2>New Market Complaint</h2>
        <button class="modal-close" onclick="document.getElementById('qms-mc-new-modal').remove()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="form-field span-2">
            <label>Title</label>
            <input type="text" id="qms-new-mc-title" placeholder="e.g. Foreign particulate reported in Batch B-2201" />
          </div>
          <div class="form-field"><label>Received Date</label><input type="date" id="qms-new-mc-received-date" /></div>
          <div class="form-field"><label>Received Via</label><select id="qms-new-mc-received-via">${qmsOptions(meta.market_complaint_received_via)}</select></div>
          <div class="form-field"><label>Complainant Name</label><input type="text" id="qms-new-mc-complainant-name" /></div>
          <div class="form-field"><label>Complainant Contact</label><input type="text" id="qms-new-mc-complainant-contact" placeholder="Phone / email / address" /></div>
          <div class="form-field"><label>Complainant Type</label><select id="qms-new-mc-complainant-type">${qmsOptions(meta.market_complaint_complainant_types)}</select></div>
          <div class="form-field"><label>Department</label><input type="text" id="qms-new-mc-dept" /></div>
          <div class="form-field"><label>Product</label><input type="text" id="qms-new-mc-product" /></div>
          <div class="form-field"><label>Batch/Lot</label><input type="text" id="qms-new-mc-batch" /></div>
          <div class="form-field"><label>Manufacturing Site</label><input type="text" id="qms-new-mc-site" /></div>
          <div class="form-field"><label>Market/Country</label><input type="text" id="qms-new-mc-market" /></div>
          <div class="form-field"><label>Regulatory Profile</label><select id="qms-new-mc-reg-profile">${qmsOptions(meta.market_complaint_regulatory_profiles)}</select></div>
          <div class="form-field span-2"><label>Description</label><textarea id="qms-new-mc-description"></textarea></div>
          <div class="form-field"><label>Initial Classification</label><select id="qms-new-mc-classification">${qmsOptions(meta.market_complaint_classifications)}</select></div>
          <div class="form-field"><label>Severity</label><select id="qms-new-mc-severity">${qmsOptions(meta.market_complaint_severities)}</select></div>
          <div class="form-field">
            <label><input type="checkbox" id="qms-new-mc-pqd" style="width:auto;margin-right:6px" /> Potential Quality Defect</label>
          </div>
          <div class="form-field">
            <label><input type="checkbox" id="qms-new-mc-pae" style="width:auto;margin-right:6px" /> Potential Adverse Event</label>
          </div>
          <div class="form-field"><label>Risk Level</label><input type="text" id="qms-new-mc-risk-level" /></div>
          <div class="form-field span-2"><label>Initial Impact Assessment</label><textarea id="qms-new-mc-impact"></textarea></div>
          <div class="form-field"><label>Immediate Containment Action</label><input type="text" id="qms-new-mc-containment-action" /></div>
          <div class="form-field"><label>Immediate Containment Date</label><input type="date" id="qms-new-mc-containment-date" /></div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="document.getElementById('qms-mc-new-modal').remove()">Cancel</button>
        <button class="btn-primary" id="qms-mc-create-btn" onclick="qmsMcCreate()">Create Complaint</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}
window.qmsMcOpenNew = qmsMcOpenNew;

async function qmsMcCreate() {
  const title = document.getElementById("qms-new-mc-title").value.trim();
  if (!title) { qmsToast("Title is required"); return; }
  const btn = document.getElementById("qms-mc-create-btn");
  if (btn.disabled) return;
  btn.disabled = true;
  const data = {
    title,
    received_date: document.getElementById("qms-new-mc-received-date").value,
    received_via: document.getElementById("qms-new-mc-received-via").value,
    complainant_name: document.getElementById("qms-new-mc-complainant-name").value.trim(),
    complainant_contact: document.getElementById("qms-new-mc-complainant-contact").value.trim(),
    complainant_type: document.getElementById("qms-new-mc-complainant-type").value,
    department: document.getElementById("qms-new-mc-dept").value.trim(),
    product: document.getElementById("qms-new-mc-product").value.trim(),
    batch_lot: document.getElementById("qms-new-mc-batch").value.trim(),
    manufacturing_site: document.getElementById("qms-new-mc-site").value.trim(),
    market_country: document.getElementById("qms-new-mc-market").value.trim(),
    regulatory_profile: document.getElementById("qms-new-mc-reg-profile").value,
    description: document.getElementById("qms-new-mc-description").value.trim(),
    initial_classification: document.getElementById("qms-new-mc-classification").value,
    severity: document.getElementById("qms-new-mc-severity").value,
    potential_quality_defect: document.getElementById("qms-new-mc-pqd").checked,
    potential_adverse_event: document.getElementById("qms-new-mc-pae").checked,
    risk_level: document.getElementById("qms-new-mc-risk-level").value.trim(),
    initial_impact_assessment: document.getElementById("qms-new-mc-impact").value.trim(),
    immediate_containment_action: document.getElementById("qms-new-mc-containment-action").value.trim(),
    immediate_containment_date: document.getElementById("qms-new-mc-containment-date").value,
  };
  try {
    const complaint = await qmsPostJSON("/qms/market-complaints", data);
    document.getElementById("qms-mc-new-modal").remove();
    qmsToast(`Created ${complaint.complaint_number}`);
    qmsMcOpenDetail(complaint.id);
  } catch (e) {
    qmsToast("Failed to create complaint: " + e.message);
    btn.disabled = false;
  }
}
window.qmsMcCreate = qmsMcCreate;

// ── Detail view ─────────────────────────────────────────────────────────────

async function qmsMcOpenDetail(id) {
  qmsMcCurrentId = id;
  qmsMcActiveTab = "overview";
  const body = document.getElementById("qms-mc-body");
  body.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading complaint…</div>`;
  try {
    const complaint = await qmsFetch(`/qms/market-complaints/${id}`);
    if (window.PharmaRecent) window.PharmaRecent.recordOpened("market_complaint", complaint.id, complaint.title, complaint.complaint_number || "");
    body.innerHTML = `
      <div class="qms-page-header">
        <div>
          <button class="btn-secondary" style="margin-bottom:10px;padding:5px 12px;font-size:12px" onclick="qmsMcShowList()">&larr; All Complaints</button>
          <div class="qms-detail-number">${complaint.complaint_number}</div>
          <div class="qms-detail-title">${complaint.title}</div>
          <div class="qms-detail-meta" id="qms-mc-meta">${qmsMcMetaHTML(complaint)}</div>
        </div>
      </div>
      <div class="qms-body">
        <div class="qms-tabs" id="qms-mc-tabs">
          ${["overview", "lifecycle", "attachments", "comments", "audit"]
            .map(t => `<button class="qms-tab ${t === qmsMcActiveTab ? "active" : ""}" onclick="qmsMcSwitchTab('${t}')">${qmsMcTabLabel(t)}</button>`).join("")}
        </div>
        <div id="qms-mc-tab-body"></div>
      </div>
    `;
    qmsMcRenderTab(complaint);
  } catch (e) {
    if (window.PharmaUI) window.PharmaUI.errorState(body, { message: `Failed to load complaint: ${e.message}`, onRetry: () => qmsMcOpenDetail(id) });
    else body.innerHTML = `<div class="qms-empty"><p>Failed to load complaint: ${e.message}</p></div>`;
  }
}
window.qmsMcOpenDetail = qmsMcOpenDetail;

function qmsMcMetaHTML(c) {
  return `
    <span>${qmsBadge(c.status)}</span>
    <span>${qmsBadge(c.severity)}</span>
    <span>Product: ${c.product || "—"}</span>
    <span>Market: ${c.market_country || "—"}</span>
    <span>Regulatory Profile: ${c.regulatory_profile || "—"}</span>
  `;
}

function qmsMcTabLabel(t) {
  return {
    overview: "Overview", lifecycle: "Lifecycle", attachments: "Attachments",
    comments: "Comments", audit: "Audit Trail",
  }[t] || t;
}

async function qmsMcSwitchTab(tab) {
  qmsMcActiveTab = tab;
  const order = ["overview", "lifecycle", "attachments", "comments", "audit"];
  document.querySelectorAll("#qms-mc-tabs .qms-tab").forEach((b, i) => b.classList.toggle("active", order[i] === tab));
  const complaint = await qmsFetch(`/qms/market-complaints/${qmsMcCurrentId}`);
  qmsMcRenderTab(complaint);
}
window.qmsMcSwitchTab = qmsMcSwitchTab;

function qmsMcRenderTab(complaint) {
  const el = document.getElementById("qms-mc-tab-body");
  const id = complaint.id;

  if (qmsMcActiveTab === "overview") {
    const meta = window.QMS_META || { market_complaint_regulatory_profiles: [] };
    el.innerHTML = `
      <div class="qms-section-card">
        <h3>Complaint Details</h3>
        <div class="form-grid">
          <div class="form-field"><label>Received Date</label><input type="date" id="qms-mcov-received-date" value="${complaint.received_date || ""}" /></div>
          <div class="form-field"><label>Complainant Name</label><input type="text" id="qms-mcov-complainant-name" value="${complaint.complainant_name || ""}" /></div>
          <div class="form-field"><label>Product</label><input type="text" id="qms-mcov-product" value="${complaint.product || ""}" /></div>
          <div class="form-field"><label>Batch/Lot</label><input type="text" id="qms-mcov-batch" value="${complaint.batch_lot || ""}" /></div>
          <div class="form-field"><label>Manufacturing Site</label><input type="text" id="qms-mcov-site" value="${complaint.manufacturing_site || ""}" /></div>
          <div class="form-field"><label>Market/Country</label><input type="text" id="qms-mcov-market" value="${complaint.market_country || ""}" /></div>
          <div class="form-field"><label>Regulatory Profile</label><select id="qms-mcov-reg-profile">${qmsOptions(meta.market_complaint_regulatory_profiles, complaint.regulatory_profile)}</select></div>
          <div class="form-field"><label>Risk Level</label><input type="text" id="qms-mcov-risk-level" value="${complaint.risk_level || ""}" /></div>
          <div class="form-field span-2"><label>Description</label><textarea id="qms-mcov-description">${complaint.description || ""}</textarea></div>
          <div class="form-field span-2"><label>Initial Impact Assessment</label><textarea id="qms-mcov-impact">${complaint.initial_impact_assessment || ""}</textarea></div>
          <div class="form-field"><label>Immediate Containment Action</label><input type="text" id="qms-mcov-containment-action" value="${complaint.immediate_containment_action || ""}" /></div>
          <div class="form-field"><label>Immediate Containment Date</label><input type="date" id="qms-mcov-containment-date" value="${complaint.immediate_containment_date || ""}" /></div>
          <div class="form-field"><label>Investigation Required</label>
            <select id="qms-mcov-investigation-required">
              <option value="" ${!complaint.investigation_required ? "selected" : ""}>—</option>
              <option value="Yes" ${complaint.investigation_required === "Yes" ? "selected" : ""}>Yes</option>
              <option value="No" ${complaint.investigation_required === "No" ? "selected" : ""}>No</option>
            </select>
          </div>
          <div class="form-field span-2"><label>Investigation Rationale (required if No)</label><textarea id="qms-mcov-investigation-rationale">${complaint.investigation_rationale || ""}</textarea></div>
        </div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsMcSaveOverview(${id})">Save</button>
        </div>
        <p style="font-size:11.5px;color:var(--text-muted);margin-top:8px">
          Investigation Engine integration (evidence, root cause, AI Assistant/Report) is a future
          release — Investigation Required/Rationale are captured here for that phase.
        </p>
      </div>
    `;
  } else if (qmsMcActiveTab === "lifecycle") {
    el.innerHTML = `<div id="qms-workflow-mc-${id}"></div>`;
    renderWorkflowPanel(`qms-workflow-mc-${id}`, "market_complaint", "/qms/market-complaints", id);
  } else if (qmsMcActiveTab === "attachments") {
    el.innerHTML = `<div id="qms-attachments-market_complaint-${id}"></div>`;
    qmsRenderAttachments(`qms-attachments-market_complaint-${id}`, "market_complaint", id);
  } else if (qmsMcActiveTab === "comments") {
    el.innerHTML = `<div id="qms-comments-market_complaint-${id}"></div>`;
    qmsRenderComments(`qms-comments-market_complaint-${id}`, "market_complaint", id);
  } else if (qmsMcActiveTab === "audit") {
    el.innerHTML = `<div id="qms-audit-market_complaint-${id}"></div>`;
    qmsRenderAuditTrail(`qms-audit-market_complaint-${id}`, "market_complaint", id);
  }
}

async function qmsMcSaveOverview(id) {
  const data = {
    received_date: document.getElementById("qms-mcov-received-date").value,
    complainant_name: document.getElementById("qms-mcov-complainant-name").value.trim(),
    product: document.getElementById("qms-mcov-product").value.trim(),
    batch_lot: document.getElementById("qms-mcov-batch").value.trim(),
    manufacturing_site: document.getElementById("qms-mcov-site").value.trim(),
    market_country: document.getElementById("qms-mcov-market").value.trim(),
    regulatory_profile: document.getElementById("qms-mcov-reg-profile").value,
    risk_level: document.getElementById("qms-mcov-risk-level").value.trim(),
    description: document.getElementById("qms-mcov-description").value,
    initial_impact_assessment: document.getElementById("qms-mcov-impact").value,
    immediate_containment_action: document.getElementById("qms-mcov-containment-action").value.trim(),
    immediate_containment_date: document.getElementById("qms-mcov-containment-date").value,
    investigation_required: document.getElementById("qms-mcov-investigation-required").value,
    investigation_rationale: document.getElementById("qms-mcov-investigation-rationale").value,
  };
  try {
    await qmsPutJSON(`/qms/market-complaints/${id}`, data);
    qmsToast("Saved");
    const metaEl = document.getElementById("qms-mc-meta");
    if (metaEl) {
      const complaint = await qmsFetch(`/qms/market-complaints/${id}`);
      metaEl.innerHTML = qmsMcMetaHTML(complaint);
    }
  } catch (e) {
    qmsToast("Save failed: " + e.message);
  }
}
window.qmsMcSaveOverview = qmsMcSaveOverview;
