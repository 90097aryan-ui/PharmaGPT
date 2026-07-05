/*
 * qms_change_control.js — Change Control module frontend (QMS Phase 2).
 *
 * Renders entirely into <main id="view-qms-change-control"><div id="qms-cc-body">.
 * Follows the same structure as qms_deviations.js/qms_capa.js, reusing
 * qms_common.js helpers (fetch wrapper, badges, meta cache, shared
 * attachments/comments/audit/approval panels).
 */

let qmsCCCurrentId = null;
let qmsCCActiveTab = "overview";

function initQMSChangeControl() {
  qmsLoadMeta().then(() => qmsCCShowList());
}
window.initQMSChangeControl = initQMSChangeControl;

// ── List view ───────────────────────────────────────────────────────────────

async function qmsCCShowList(filters = {}) {
  qmsCCCurrentId = null;
  const body = document.getElementById("qms-cc-body");
  body.innerHTML = `
    <div class="qms-page-header">
      <div>
        <h2>Change Control</h2>
        <p>Equipment, facility, utility, software, and process changes — draft through closure</p>
      </div>
      <div class="qms-header-actions">
        <button class="btn-primary" onclick="qmsCCOpenNew()">+ New Change Control</button>
      </div>
    </div>
    <div class="qms-body">
      <div id="qms-cc-toolbar"></div>
      <div id="qms-cc-list-container"><div class="qms-loading"><div class="qms-spinner"></div> Loading change controls…</div></div>
    </div>
  `;
  renderQMSCCToolbar(filters);
  await qmsCCLoadList(filters);
}
window.qmsCCShowList = qmsCCShowList;

function renderQMSCCToolbar(filters) {
  const meta = window.QMS_META || { change_types: [], change_categories: [], change_control_statuses: [] };
  const el = document.getElementById("qms-cc-toolbar");
  el.innerHTML = `
    <div class="qms-toolbar">
      <input type="text" id="qms-cc-search" placeholder="Search by title, number, or description…" value="${filters.q || ""}" />
      <select id="qms-cc-filter-type">
        <option value="">All Types</option>
        ${qmsOptions(meta.change_types, filters.type)}
      </select>
      <select id="qms-cc-filter-category">
        <option value="">All Categories</option>
        ${qmsOptions(meta.change_categories, filters.category)}
      </select>
      <select id="qms-cc-filter-status">
        <option value="">All Statuses</option>
        ${qmsOptions(meta.change_control_statuses, filters.status)}
      </select>
      <button class="btn-secondary" onclick="qmsCCApplyFilters()">Filter</button>
    </div>
  `;
  document.getElementById("qms-cc-search").addEventListener("keydown", e => {
    if (e.key === "Enter") qmsCCApplyFilters();
  });
}

function qmsCCApplyFilters() {
  const filters = {
    q: document.getElementById("qms-cc-search").value.trim(),
    type: document.getElementById("qms-cc-filter-type").value,
    category: document.getElementById("qms-cc-filter-category").value,
    status: document.getElementById("qms-cc-filter-status").value,
  };
  qmsCCLoadList(filters);
}
window.qmsCCApplyFilters = qmsCCApplyFilters;

async function qmsCCLoadList(filters = {}) {
  const container = document.getElementById("qms-cc-list-container");
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.type) params.set("type", filters.type);
  if (filters.category) params.set("category", filters.category);
  if (filters.status) params.set("status", filters.status);

  try {
    const changes = await qmsFetch(`/qms/change-control?${params.toString()}`);
    if (!changes.length) {
      container.innerHTML = `
        <div class="qms-empty">
          <div class="qms-empty-icon"><span class='icon' data-lucide='git-pull-request'></span></div>
          <h3>No change controls yet</h3>
          <p>Initiate your first change control to get started.</p>
        </div>`;
      return;
    }
    container.innerHTML = `
      <table class="qms-table">
        <thead><tr><th>CC Number</th><th>Title</th><th>Type</th><th>Category</th><th>Department</th><th>Status</th><th>Target Date</th></tr></thead>
        <tbody>
          ${changes.map(c => `
            <tr class="clickable" onclick="qmsCCOpenDetail(${c.id})">
              <td>${c.cc_number}</td>
              <td>${c.title}</td>
              <td>${qmsBadge(c.change_type)}</td>
              <td>${c.change_category}</td>
              <td>${c.department || "—"}</td>
              <td>${qmsBadge(c.status)}</td>
              <td>${c.target_implementation_date || "—"}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    container.innerHTML = `<div class="qms-empty"><p>Failed to load change controls: ${e.message}</p></div>`;
  }
}

// ── Create wizard ───────────────────────────────────────────────────────────

function qmsCCOpenNew() {
  const meta = window.QMS_META || { change_types: [], change_categories: [] };
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";
  overlay.id = "qms-cc-new-modal";
  overlay.innerHTML = `
    <div class="modal open qms-modal-lg">
      <div class="modal-header">
        <h2>New Change Control</h2>
        <button class="modal-close" onclick="document.getElementById('qms-cc-new-modal').remove()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="form-field span-2">
            <label>Title</label>
            <input type="text" id="qms-new-cc-title" placeholder="e.g. Upgrade HVAC controller firmware in Suite 3" />
          </div>
          <div class="form-field">
            <label>Change Type</label>
            <select id="qms-new-cc-type">${qmsOptions(meta.change_types, "Minor")}</select>
          </div>
          <div class="form-field">
            <label>Change Category</label>
            <select id="qms-new-cc-category">${qmsOptions(meta.change_categories, "Equipment")}</select>
          </div>
          <div class="form-field">
            <label>Department</label>
            <input type="text" id="qms-new-cc-dept" />
          </div>
          <div class="form-field">
            <label>Area</label>
            <input type="text" id="qms-new-cc-area" />
          </div>
          <div class="form-field">
            <label>Equipment / System</label>
            <input type="text" id="qms-new-cc-equipment" />
          </div>
          <div class="form-field">
            <label>Requested By</label>
            <input type="text" id="qms-new-cc-requestedby" />
          </div>
          <div class="form-field">
            <label>Date Requested</label>
            <input type="date" id="qms-new-cc-date" />
          </div>
          <div class="form-field">
            <label>Target Implementation Date</label>
            <input type="date" id="qms-new-cc-target-date" />
          </div>
          <div class="form-field span-2">
            <label>Change Description</label>
            <textarea id="qms-new-cc-desc" placeholder="What is changing?"></textarea>
          </div>
          <div class="form-field span-2">
            <label>Reason for Change</label>
            <textarea id="qms-new-cc-reason"></textarea>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="document.getElementById('qms-cc-new-modal').remove()">Cancel</button>
        <button class="btn-primary" onclick="qmsCCCreate()">Create Change Control</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}
window.qmsCCOpenNew = qmsCCOpenNew;

async function qmsCCCreate() {
  const title = document.getElementById("qms-new-cc-title").value.trim();
  if (!title) { qmsToast("Title is required"); return; }
  const data = {
    title,
    change_type: document.getElementById("qms-new-cc-type").value,
    change_category: document.getElementById("qms-new-cc-category").value,
    department: document.getElementById("qms-new-cc-dept").value.trim(),
    area: document.getElementById("qms-new-cc-area").value.trim(),
    equipment_system: document.getElementById("qms-new-cc-equipment").value.trim(),
    requested_by: document.getElementById("qms-new-cc-requestedby").value.trim(),
    date_requested: document.getElementById("qms-new-cc-date").value,
    target_implementation_date: document.getElementById("qms-new-cc-target-date").value,
    change_description: document.getElementById("qms-new-cc-desc").value.trim(),
    reason_for_change: document.getElementById("qms-new-cc-reason").value.trim(),
  };
  try {
    const cc = await qmsPostJSON("/qms/change-control", data);
    document.getElementById("qms-cc-new-modal").remove();
    qmsToast(`Created ${cc.cc_number}`);
    qmsCCOpenDetail(cc.id);
  } catch (e) {
    qmsToast("Failed to create change control: " + e.message);
  }
}
window.qmsCCCreate = qmsCCCreate;

// ── Detail view ─────────────────────────────────────────────────────────────

const QMS_CC_TABS = ["overview", "impact", "plan", "ai", "links", "attachments", "comments", "audit", "approval"];

async function qmsCCOpenDetail(id) {
  qmsCCCurrentId = id;
  qmsCCActiveTab = "overview";
  const body = document.getElementById("qms-cc-body");
  body.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading change control…</div>`;
  try {
    const cc = await qmsFetch(`/qms/change-control/${id}`);
    body.innerHTML = `
      <div class="qms-page-header">
        <div>
          <button class="btn-secondary" style="margin-bottom:10px;padding:5px 12px;font-size:12px" onclick="qmsCCShowList()">&larr; All Change Controls</button>
          <div class="qms-detail-number">${cc.cc_number} · ${cc.change_type} · ${cc.change_category}</div>
          <div class="qms-detail-title">${cc.title}</div>
          <div class="qms-detail-meta" id="qms-cc-meta">
            ${qmsCCMetaHTML(cc)}
          </div>
        </div>
        <div class="qms-header-actions">
          <button class="btn-secondary" onclick="qmsCCPrint(${id})">Print</button>
          <button class="btn-secondary" onclick="qmsCCExportDocx(${id})">Export DOCX</button>
        </div>
      </div>
      <div class="qms-body">
        <div class="qms-tabs" id="qms-cc-tabs">
          ${QMS_CC_TABS.map(t => `<button class="qms-tab ${t === qmsCCActiveTab ? "active" : ""}" onclick="qmsCCSwitchTab('${t}')">${qmsCCTabLabel(t)}</button>`).join("")}
        </div>
        <div id="qms-cc-tab-body"></div>
      </div>
    `;
    qmsCCRenderTab(cc);
  } catch (e) {
    body.innerHTML = `<div class="qms-empty"><p>Failed to load change control: ${e.message}</p></div>`;
  }
}
window.qmsCCOpenDetail = qmsCCOpenDetail;

function qmsCCMetaHTML(cc) {
  return `
    <span>${qmsBadge(cc.status)}</span>
    <span>Department: ${cc.department || "—"}</span>
    <span>Equipment/System: ${cc.equipment_system || "—"}</span>
    <span>Requested by: ${cc.requested_by || "—"}</span>
  `;
}

function qmsCCTabLabel(t) {
  return {
    overview: "Overview", impact: "Impact Assessment", plan: "Implementation Plan",
    ai: "AI Assistant", links: "Related Records", attachments: "Attachments",
    comments: "Comments", audit: "Audit Trail", approval: "Approval",
  }[t] || t;
}

async function qmsCCSwitchTab(tab) {
  qmsCCActiveTab = tab;
  document.querySelectorAll("#qms-cc-tabs .qms-tab").forEach((b, i) => b.classList.toggle("active", QMS_CC_TABS[i] === tab));
  const cc = await qmsFetch(`/qms/change-control/${qmsCCCurrentId}`);
  qmsCCRenderTab(cc);
}
window.qmsCCSwitchTab = qmsCCSwitchTab;

function qmsCCRenderTab(cc) {
  const el = document.getElementById("qms-cc-tab-body");
  const id = cc.id;

  if (qmsCCActiveTab === "overview") {
    el.innerHTML = `
      <div class="qms-section-card">
        <h3>Change Control Details</h3>
        <div class="form-grid">
          <div class="form-field"><label>Area</label><input type="text" id="qms-cco-area" value="${cc.area || ""}" /></div>
          <div class="form-field"><label>Equipment/System</label><input type="text" id="qms-cco-equipment" value="${cc.equipment_system || ""}" /></div>
          <div class="form-field"><label>Risk Level</label><input type="text" id="qms-cco-risk" value="${cc.risk_level || ""}" /></div>
          <div class="form-field"><label>QA Reviewer</label><input type="text" id="qms-cco-qa" value="${cc.qa_reviewer || ""}" /></div>
          <div class="form-field span-2"><label>Change Description</label><textarea id="qms-cco-desc">${cc.change_description || ""}</textarea></div>
          <div class="form-field span-2"><label>Reason for Change</label><textarea id="qms-cco-reason">${cc.reason_for_change || ""}</textarea></div>
          <div class="form-field span-2"><label>Current State</label><textarea id="qms-cco-current">${cc.current_state || ""}</textarea></div>
          <div class="form-field span-2"><label>Proposed State</label><textarea id="qms-cco-proposed">${cc.proposed_state || ""}</textarea></div>
        </div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsCCSaveOverview(${id})">Save</button>
        </div>
      </div>
    `;
  } else if (qmsCCActiveTab === "impact") {
    qmsCCRenderImpact(id);
  } else if (qmsCCActiveTab === "plan") {
    qmsCCRenderPlan(id);
  } else if (qmsCCActiveTab === "ai") {
    qmsCCRenderAI(cc);
  } else if (qmsCCActiveTab === "links") {
    qmsCCRenderLinks(id);
  } else if (qmsCCActiveTab === "attachments") {
    el.innerHTML = `<div id="qms-attachments-change_control-${id}"></div>`;
    qmsRenderAttachments(`qms-attachments-change_control-${id}`, "change_control", id);
  } else if (qmsCCActiveTab === "comments") {
    el.innerHTML = `<div id="qms-comments-change_control-${id}"></div>`;
    qmsRenderComments(`qms-comments-change_control-${id}`, "change_control", id);
  } else if (qmsCCActiveTab === "audit") {
    el.innerHTML = `<div id="qms-audit-change_control-${id}"></div>`;
    qmsRenderAuditTrail(`qms-audit-change_control-${id}`, "change_control", id);
  } else if (qmsCCActiveTab === "approval") {
    el.innerHTML = `<div id="qms-approval-change_control-${id}"></div>`;
    qmsCCRenderApprovalTab(id);
  }
}

async function qmsCCSaveOverview(id) {
  const data = {
    area: document.getElementById("qms-cco-area").value.trim(),
    equipment_system: document.getElementById("qms-cco-equipment").value.trim(),
    risk_level: document.getElementById("qms-cco-risk").value.trim(),
    qa_reviewer: document.getElementById("qms-cco-qa").value.trim(),
    change_description: document.getElementById("qms-cco-desc").value,
    reason_for_change: document.getElementById("qms-cco-reason").value,
    current_state: document.getElementById("qms-cco-current").value,
    proposed_state: document.getElementById("qms-cco-proposed").value,
  };
  try {
    await qmsPutJSON(`/qms/change-control/${id}`, data);
    qmsToast("Saved");
  } catch (e) {
    qmsToast("Save failed: " + e.message);
  }
}
window.qmsCCSaveOverview = qmsCCSaveOverview;

// ── Impact assessment tab ──────────────────────────────────────────────────────

async function qmsCCRenderImpact(id) {
  const el = document.getElementById("qms-cc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading impact assessment…</div>`;
  const impacts = await qmsFetch(`/qms/change-control/${id}/impact`);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>AI Impact Assessment</h3>
      <p style="font-size:12.5px;color:var(--text-muted);margin-bottom:12px">
        Assesses impact across Validation, Qualification, Risk, URS, SOP, Training, Equipment,
        Documents, Software, Utilities, Regulatory Compliance, Business Continuity, Electronic
        Records, and Electronic Signatures.
      </p>
      <button class="btn-primary" onclick="qmsCCSuggestImpact(${id})"><span class='icon' data-lucide='sparkles'></span> Run AI Impact Assessment</button>
      <div id="qms-cc-impact-suggestions" style="margin-top:12px"></div>
    </div>
    <div class="qms-section-card">
      <h3>Add Impact Assessment Entry</h3>
      <div class="form-grid">
        <div class="form-field"><label>Impact Area</label><input type="text" id="qms-cc-impact-area" placeholder="e.g. Validation" /></div>
        <div class="form-field"><label>Impacted?</label><input type="text" id="qms-cc-impact-flag" placeholder="Yes / No / Potential" /></div>
        <div class="form-field span-2"><label>Extent</label><textarea id="qms-cc-impact-extent"></textarea></div>
        <div class="form-field span-2"><label>Action Required</label><input type="text" id="qms-cc-impact-action" /></div>
      </div>
      <div class="qms-form-actions">
        <button class="btn-primary" onclick="qmsCCAddImpact(${id})">Add</button>
      </div>
    </div>
    ${impacts.length ? `
      <table class="qms-table">
        <thead><tr><th>Impact Area</th><th>Impacted?</th><th>Extent</th><th>Action Required</th></tr></thead>
        <tbody>${impacts.map(i => `<tr><td>${i.impact_area}</td><td>${qmsBadge(i.impacted)}</td><td>${i.extent || "—"}</td><td>${i.action_required || "—"}</td></tr>`).join("")}</tbody>
      </table>` : `<div class="qms-empty"><p>No impact assessment entries yet.</p></div>`}
  `;
}

async function qmsCCSuggestImpact(id) {
  const el = document.getElementById("qms-cc-impact-suggestions");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Generating suggestions…</div>`;
  try {
    const suggestions = await qmsPostJSON(`/qms/change-control/${id}/suggest-impact`, {});
    el.innerHTML = suggestions.length ? suggestions.map(s => `
      <div class="qms-panel-item">
        <div>
          <strong>${s.impact_area}</strong> — ${qmsBadge(s.impacted)}
          <div>${s.extent || ""}</div>
          <div class="qms-panel-item-meta">Action: ${s.action_required || "—"}</div>
        </div>
        <button class="btn-secondary" style="padding:5px 12px;font-size:11px" onclick='qmsCCAcceptImpactSuggestion(${id}, ${JSON.stringify(s).replace(/'/g, "&apos;")})'>Add to Record</button>
      </div>`).join("") : `<p style="font-size:12.5px;color:var(--text-muted)">No suggestions returned.</p>`;
  } catch (e) {
    el.innerHTML = `<p style="font-size:12.5px;color:var(--text-muted)">Failed: ${e.message}</p>`;
  }
}
window.qmsCCSuggestImpact = qmsCCSuggestImpact;

async function qmsCCAcceptImpactSuggestion(id, suggestion) {
  try {
    await qmsPostJSON(`/qms/change-control/${id}/impact`, suggestion);
    qmsToast("Added to record");
    qmsCCRenderImpact(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCCAcceptImpactSuggestion = qmsCCAcceptImpactSuggestion;

async function qmsCCAddImpact(id) {
  const data = {
    impact_area: document.getElementById("qms-cc-impact-area").value.trim(),
    impacted: document.getElementById("qms-cc-impact-flag").value.trim() || "Potential",
    extent: document.getElementById("qms-cc-impact-extent").value.trim(),
    action_required: document.getElementById("qms-cc-impact-action").value.trim(),
  };
  if (!data.impact_area) { qmsToast("Impact area is required"); return; }
  try {
    await qmsPostJSON(`/qms/change-control/${id}/impact`, data);
    qmsCCRenderImpact(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCCAddImpact = qmsCCAddImpact;

// ── Implementation plan tab ───────────────────────────────────────────────────

async function qmsCCRenderPlan(id) {
  const el = document.getElementById("qms-cc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading implementation plan…</div>`;
  const actions = await qmsFetch(`/qms/change-control/${id}/actions`);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>AI Implementation Plan / Checklist</h3>
      <button class="btn-primary" onclick="qmsCCSuggestPlan(${id})"><span class='icon' data-lucide='sparkles'></span> Suggest Implementation Steps with AI</button>
      <div id="qms-cc-plan-suggestions" style="margin-top:12px"></div>
    </div>
    <div class="qms-section-card">
      <h3>Add Implementation Step</h3>
      <div class="form-grid cols-3">
        <div class="form-field"><label>Step #</label><input type="number" id="qms-cc-plan-step" value="${actions.length + 1}" /></div>
        <div class="form-field span-2"><label>Activity</label><input type="text" id="qms-cc-plan-activity" /></div>
        <div class="form-field"><label>Responsible</label><input type="text" id="qms-cc-plan-responsible" /></div>
        <div class="form-field"><label>Target Date</label><input type="date" id="qms-cc-plan-target" /></div>
      </div>
      <div class="qms-form-actions">
        <button class="btn-primary" onclick="qmsCCAddAction(${id})">Add Step</button>
      </div>
    </div>
    ${actions.length ? `
      <table class="qms-table">
        <thead><tr><th>#</th><th>Activity</th><th>Responsible</th><th>Target Date</th><th>Status</th></tr></thead>
        <tbody>${actions.map(a => `<tr><td>${a.step_no}</td><td>${a.activity}</td><td>${a.responsible || "—"}</td><td>${a.target_date || "—"}</td><td>
          <select onchange="qmsCCUpdateActionStatus(${id},${a.id},this.value)">
            ${["Pending","In Progress","Completed","Overdue"].map(s => `<option value="${s}" ${s === a.status ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </td></tr>`).join("")}</tbody>
      </table>` : `<div class="qms-empty"><p>No implementation steps recorded yet.</p></div>`}
  `;
}

async function qmsCCSuggestPlan(id) {
  const el = document.getElementById("qms-cc-plan-suggestions");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Generating implementation plan…</div>`;
  try {
    const suggestions = await qmsPostJSON(`/qms/change-control/${id}/suggest-implementation-plan`, {});
    el.innerHTML = suggestions.length ? `
      <div class="qms-panel-item" style="flex-direction:column;align-items:stretch">
        ${suggestions.map(s => `<div>Step ${s.step_no}: <strong>${s.activity}</strong> — ${s.responsible || ""}</div>`).join("")}
        <div class="qms-form-actions">
          <button class="btn-primary" onclick='qmsCCAcceptPlanSuggestions(${id}, ${JSON.stringify(suggestions).replace(/'/g, "&apos;")})'>Add All Steps to Plan</button>
        </div>
      </div>
    ` : `<p style="font-size:12.5px;color:var(--text-muted)">No suggestions returned.</p>`;
  } catch (e) {
    el.innerHTML = `<p style="font-size:12.5px;color:var(--text-muted)">Failed: ${e.message}</p>`;
  }
}
window.qmsCCSuggestPlan = qmsCCSuggestPlan;

async function qmsCCAcceptPlanSuggestions(id, suggestions) {
  try {
    for (const s of suggestions) {
      await qmsPostJSON(`/qms/change-control/${id}/actions`, {
        step_no: s.step_no, activity: s.activity, responsible: s.responsible || "",
      });
    }
    qmsToast("Implementation plan added");
    qmsCCRenderPlan(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCCAcceptPlanSuggestions = qmsCCAcceptPlanSuggestions;

async function qmsCCAddAction(id) {
  const data = {
    step_no: parseInt(document.getElementById("qms-cc-plan-step").value, 10) || 0,
    activity: document.getElementById("qms-cc-plan-activity").value.trim(),
    responsible: document.getElementById("qms-cc-plan-responsible").value.trim(),
    target_date: document.getElementById("qms-cc-plan-target").value,
  };
  if (!data.activity) { qmsToast("Activity is required"); return; }
  try {
    await qmsPostJSON(`/qms/change-control/${id}/actions`, data);
    qmsCCRenderPlan(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCCAddAction = qmsCCAddAction;

async function qmsCCUpdateActionStatus(id, actionId, status) {
  try {
    await qmsPostJSON(`/qms/change-control/${id}/actions`, { id: actionId, status });
    qmsToast("Status updated");
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCCUpdateActionStatus = qmsCCUpdateActionStatus;

// ── AI Assistant tab (narrative features) ─────────────────────────────────────

const QMS_CC_NARRATIVES = [
  { key: "risk_summary", path: "risk-summary", label: "Risk Summary" },
  { key: "rollback_plan", path: "rollback-plan", label: "Rollback Plan" },
  { key: "regulatory_impact", path: "regulatory-impact", label: "Regulatory Impact" },
  { key: "justification", path: "justification", label: "Change Justification" },
  { key: "executive_summary", path: "executive-summary", label: "Executive Summary" },
  { key: "verification_summary", path: "verification-summary", label: "Verification Summary" },
  { key: "effectiveness_review", path: "effectiveness-review", label: "Effectiveness Review" },
];

function qmsCCRenderAI(cc) {
  const el = document.getElementById("qms-cc-tab-body");
  const narratives = cc.ai_narratives || {};
  el.innerHTML = `
    <div class="qms-section-card">
      <h3><span class='icon' data-lucide='sparkles'></span> AI Assistant</h3>
      <p style="font-size:12.5px;color:var(--text-muted)">
        Optional Gemini-backed drafting assistance. Every output below is editable context, not a
        substitute for QA judgment — review before relying on it for approval decisions.
      </p>
    </div>
    ${QMS_CC_NARRATIVES.map(n => `
      <div class="qms-section-card">
        <h3>${n.label}</h3>
        <button class="btn-secondary" id="qms-cc-ai-btn-${n.key}" onclick="qmsCCRunNarrative(${cc.id}, '${n.path}', '${n.key}')">
          <span class='icon' data-lucide='sparkles'></span> ${narratives[n.key] ? "Regenerate" : "Generate"}
        </button>
        <div class="qms-ai-output" id="qms-cc-ai-output-${n.key}" style="margin-top:10px">${narratives[n.key] || "<em>Not generated yet.</em>"}</div>
      </div>
    `).join("")}
  `;
}

async function qmsCCRunNarrative(id, path, key) {
  const btn = document.getElementById(`qms-cc-ai-btn-${key}`);
  const out = document.getElementById(`qms-cc-ai-output-${key}`);
  if (btn) btn.disabled = true;
  out.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Generating…</div>`;
  try {
    const res = await qmsPostJSON(`/qms/change-control/${id}/${path}`, {});
    out.textContent = res.text;
    qmsToast(`${key.replace(/_/g, " ")} generated`);
  } catch (e) {
    out.innerHTML = `<em>Failed: ${e.message}</em>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}
window.qmsCCRunNarrative = qmsCCRunNarrative;

// ── Related records tab (Deviation / CAPA linkage) ────────────────────────────

async function qmsCCRenderLinks(id) {
  const el = document.getElementById("qms-cc-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading related records…</div>`;
  const [deviations, capas] = await Promise.all([
    qmsFetch(`/qms/change-control/${id}/deviations`),
    qmsFetch(`/qms/change-control/${id}/capas`),
  ]);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Link an Existing Deviation</h3>
      <div class="form-grid cols-3">
        <div class="form-field span-2"><label>Deviation ID</label><input type="number" id="qms-cc-link-dev-id" placeholder="Numeric deviation ID" /></div>
        <div class="form-field" style="align-self:flex-end"><button class="btn-primary" onclick="qmsCCLinkDeviation(${id})">Link</button></div>
      </div>
      ${deviations.length ? `
        <table class="qms-table">
          <thead><tr><th>Deviation Number</th><th>Title</th><th>Status</th></tr></thead>
          <tbody>${deviations.map(d => `<tr><td>${d.deviation_number}</td><td>${d.title}</td><td>${qmsBadge(d.status)}</td></tr>`).join("")}</tbody>
        </table>` : `<div class="qms-empty"><p>No deviations linked yet.</p></div>`}
    </div>
    <div class="qms-section-card">
      <h3>Link an Existing CAPA</h3>
      <div class="form-grid cols-3">
        <div class="form-field span-2"><label>CAPA ID</label><input type="number" id="qms-cc-link-capa-id" placeholder="Numeric CAPA ID" /></div>
        <div class="form-field" style="align-self:flex-end"><button class="btn-primary" onclick="qmsCCLinkCapa(${id})">Link</button></div>
      </div>
      ${capas.length ? `
        <table class="qms-table">
          <thead><tr><th>CAPA Number</th><th>Title</th><th>Status</th></tr></thead>
          <tbody>${capas.map(c => `<tr><td>${c.capa_number}</td><td>${c.title}</td><td>${qmsBadge(c.status)}</td></tr>`).join("")}</tbody>
        </table>` : `<div class="qms-empty"><p>No CAPAs linked yet.</p></div>`}
    </div>
  `;
}

async function qmsCCLinkDeviation(id) {
  const devId = parseInt(document.getElementById("qms-cc-link-dev-id").value, 10);
  if (!devId) { qmsToast("Enter a valid deviation ID"); return; }
  try {
    await qmsPostJSON(`/qms/change-control/${id}/link-deviation`, { deviation_id: devId });
    qmsToast("Deviation linked");
    qmsCCRenderLinks(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCCLinkDeviation = qmsCCLinkDeviation;

async function qmsCCLinkCapa(id) {
  const capaId = parseInt(document.getElementById("qms-cc-link-capa-id").value, 10);
  if (!capaId) { qmsToast("Enter a valid CAPA ID"); return; }
  try {
    await qmsPostJSON(`/qms/change-control/${id}/link-capa`, { capa_id: capaId });
    qmsToast("CAPA linked");
    qmsCCRenderLinks(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCCLinkCapa = qmsCCLinkCapa;

// ── Approval / status transition ──────────────────────────────────────────────

async function qmsCCRenderApprovalTab(id) {
  const actions = [
    "Submitted", "Initial Review Started", "Impact Assessment Started", "Risk Assessment Started",
    "Sent for Department Review", "Submitted for QA Review", "Sent for Approval", "Approved",
    "Rejected", "Implementation Complete", "Verified", "Closed",
  ];
  qmsRenderApproval(`qms-approval-change_control-${id}`, "change_control", id, actions, `/qms/change-control/${id}/approval`,
    () => qmsCCRefreshApprovalTab(id));
}

async function qmsCCRefreshApprovalTab(id) {
  const cc = await qmsFetch(`/qms/change-control/${id}`);
  const metaEl = document.getElementById("qms-cc-meta");
  if (metaEl) metaEl.innerHTML = qmsCCMetaHTML(cc);
  qmsCCRenderApprovalTab(id);
}

// ── Print / Export ──────────────────────────────────────────────────────────

async function qmsCCPrint(id) {
  try {
    const { markdown, title } = await qmsFetch(`/qms/change-control/${id}/report`);
    const win = window.open("", "_blank");
    win.document.write(`<html><head><title>${title}</title></head><body>${window.marked ? marked.parse(markdown) : `<pre>${markdown}</pre>`}</body></html>`);
    win.document.close();
    win.print();
  } catch (e) {
    qmsToast("Failed to prepare print view: " + e.message);
  }
}
window.qmsCCPrint = qmsCCPrint;

async function qmsCCExportDocx(id) {
  try {
    const res = await fetch(`/qms/change-control/${id}/export/docx`, { method: "POST" });
    if (!res.ok) { qmsToast("Export failed"); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `ChangeControl_${id}.docx`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    qmsToast("Export error: " + e.message);
  }
}
window.qmsCCExportDocx = qmsCCExportDocx;
