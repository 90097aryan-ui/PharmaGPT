/*
 * qms_deviations.js — Deviation Management module frontend.
 *
 * Renders entirely into <main id="view-qms-deviations"><div id="qms-deviations-body">.
 * Follows the same structure as qms_documents.js, reusing qms_common.js helpers.
 */

let qmsDevCurrentId = null;
let qmsDevActiveTab = "overview";

function initQMSDeviations() {
  qmsLoadMeta().then(() => qmsDevShowList());
}
window.initQMSDeviations = initQMSDeviations;

// ── List view ───────────────────────────────────────────────────────────────

async function qmsDevShowList(filters = {}) {
  qmsDevCurrentId = null;
  const body = document.getElementById("qms-deviations-body");
  body.innerHTML = `
    <div class="qms-page-header">
      <div>
        <h2>Deviation Management</h2>
        <p>Minor, Major, Critical, and Market deviations — investigation through closure</p>
      </div>
      <div class="qms-header-actions">
        <button class="btn-primary" onclick="qmsDevOpenNew()">+ New Deviation</button>
      </div>
    </div>
    <div class="qms-body">
      <div id="qms-dev-toolbar"></div>
      <div id="qms-dev-list-container"><div class="qms-loading"><div class="qms-spinner"></div> Loading deviations…</div></div>
    </div>
  `;
  renderQMSDevToolbar(filters);
  await qmsDevLoadList(filters);
}
window.qmsDevShowList = qmsDevShowList;

function renderQMSDevToolbar(filters) {
  const meta = window.QMS_META || { deviation_types: [], deviation_categories: [], deviation_statuses: [] };
  const el = document.getElementById("qms-dev-toolbar");
  el.innerHTML = `
    <div class="qms-toolbar">
      <input type="text" id="qms-dev-search" placeholder="Search by title, number, or description…" value="${filters.q || ""}" />
      <select id="qms-dev-filter-type">
        <option value="">All Types</option>
        ${qmsOptions(meta.deviation_types, filters.type)}
      </select>
      <select id="qms-dev-filter-category">
        <option value="">All Categories</option>
        ${qmsOptions(meta.deviation_categories, filters.category)}
      </select>
      <select id="qms-dev-filter-status">
        <option value="">All Statuses</option>
        ${qmsOptions(meta.deviation_statuses, filters.status)}
      </select>
      <button class="btn-secondary" onclick="qmsDevApplyFilters()">Filter</button>
    </div>
  `;
  document.getElementById("qms-dev-search").addEventListener("keydown", e => {
    if (e.key === "Enter") qmsDevApplyFilters();
  });
}

function qmsDevApplyFilters() {
  const filters = {
    q: document.getElementById("qms-dev-search").value.trim(),
    type: document.getElementById("qms-dev-filter-type").value,
    category: document.getElementById("qms-dev-filter-category").value,
    status: document.getElementById("qms-dev-filter-status").value,
  };
  qmsDevLoadList(filters);
}
window.qmsDevApplyFilters = qmsDevApplyFilters;

async function qmsDevLoadList(filters = {}) {
  const container = document.getElementById("qms-dev-list-container");
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.type) params.set("type", filters.type);
  if (filters.category) params.set("category", filters.category);
  if (filters.status) params.set("status", filters.status);

  try {
    const devs = await qmsFetch(`/qms/deviations?${params.toString()}`);
    if (!devs.length) {
      container.innerHTML = `
        <div class="qms-empty">
          <div class="qms-empty-icon"><span class=\'icon\' data-lucide=\'zap\'></span></div>
          <h3>No deviations yet</h3>
          <p>Initiate your first deviation to get started.</p>
        </div>`;
      return;
    }
    container.innerHTML = `
      <table class="qms-table">
        <thead><tr><th>Dev Number</th><th>Title</th><th>Type</th><th>Category</th><th>Department</th><th>Status</th><th>Reported</th></tr></thead>
        <tbody>
          ${devs.map(d => `
            <tr class="clickable" onclick="qmsDevOpenDetail(${d.id})">
              <td>${d.deviation_number}</td>
              <td>${d.title}</td>
              <td>${qmsBadge(d.deviation_type)}</td>
              <td>${d.deviation_category}</td>
              <td>${d.department || "—"}</td>
              <td>${qmsBadge(d.status)}</td>
              <td>${d.date_reported || "—"}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    if (window.PharmaUI) window.PharmaUI.errorState(container, { message: `Failed to load deviations: ${e.message}`, onRetry: () => qmsDevLoadList(filters) });
    else container.innerHTML = `<div class="qms-empty"><p>Failed to load deviations: ${e.message}</p></div>`;
  }
}

// ── Create wizard ───────────────────────────────────────────────────────────

function qmsDevOpenNew() {
  if (window.PharmaAuth && !window.PharmaAuth.requireCompanyContext()) return;
  const meta = window.QMS_META || { deviation_types: [], deviation_categories: [] };
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";
  overlay.id = "qms-dev-new-modal";
  overlay.innerHTML = `
    <div class="modal open qms-modal-lg">
      <div class="modal-header">
        <h2>New Deviation</h2>
        <button class="modal-close" onclick="document.getElementById('qms-dev-new-modal').remove()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="form-field span-2">
            <label>Title</label>
            <input type="text" id="qms-new-dev-title" placeholder="e.g. Temperature excursion in cold storage" />
          </div>
          <div class="form-field">
            <label>Deviation Type</label>
            <select id="qms-new-dev-type">${qmsOptions(meta.deviation_types, "Minor")}</select>
          </div>
          <div class="form-field">
            <label>Category</label>
            <select id="qms-new-dev-category">${qmsOptions(meta.deviation_categories, "Manufacturing")}</select>
          </div>
          <div class="form-field">
            <label>Department</label>
            <input type="text" id="qms-new-dev-dept" />
          </div>
          <div class="form-field">
            <label>Area</label>
            <input type="text" id="qms-new-dev-area" />
          </div>
          <div class="form-field">
            <label>Product</label>
            <input type="text" id="qms-new-dev-product" />
          </div>
          <div class="form-field">
            <label>Batch/Lot</label>
            <input type="text" id="qms-new-dev-batch" />
          </div>
          <div class="form-field">
            <label>Equipment</label>
            <input type="text" id="qms-new-dev-equipment" />
          </div>
          <div class="form-field">
            <label>Date of Occurrence</label>
            <input type="date" id="qms-new-dev-date" />
          </div>
          <div class="form-field span-2">
            <label>Description</label>
            <textarea id="qms-new-dev-desc" placeholder="What happened?"></textarea>
          </div>
          <div class="form-field span-2">
            <label>Immediate Action Taken</label>
            <textarea id="qms-new-dev-action"></textarea>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="document.getElementById('qms-dev-new-modal').remove()">Cancel</button>
        <button class="btn-primary" id="qms-dev-create-btn" onclick="qmsDevCreate()">Create Deviation</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}
window.qmsDevOpenNew = qmsDevOpenNew;

async function qmsDevCreate() {
  const title = document.getElementById("qms-new-dev-title").value.trim();
  if (!title) { qmsToast("Title is required"); return; }
  const btn = document.getElementById("qms-dev-create-btn");
  if (btn.disabled) return;
  btn.disabled = true;
  const data = {
    title,
    deviation_type: document.getElementById("qms-new-dev-type").value,
    deviation_category: document.getElementById("qms-new-dev-category").value,
    department: document.getElementById("qms-new-dev-dept").value.trim(),
    area: document.getElementById("qms-new-dev-area").value.trim(),
    product: document.getElementById("qms-new-dev-product").value.trim(),
    batch_lot: document.getElementById("qms-new-dev-batch").value.trim(),
    equipment: document.getElementById("qms-new-dev-equipment").value.trim(),
    date_of_occurrence: document.getElementById("qms-new-dev-date").value,
    description: document.getElementById("qms-new-dev-desc").value.trim(),
    immediate_action: document.getElementById("qms-new-dev-action").value.trim(),
  };
  try {
    const dev = await qmsPostJSON("/qms/deviations", data);
    document.getElementById("qms-dev-new-modal").remove();
    qmsToast(`Created ${dev.deviation_number}`);
    qmsDevOpenDetail(dev.id, "lifecycle");
  } catch (e) {
    qmsToast("Failed to create deviation: " + e.message);
    btn.disabled = false;
  }
}
window.qmsDevCreate = qmsDevCreate;

// ── Detail view ─────────────────────────────────────────────────────────────

async function qmsDevOpenDetail(id, initialTab = "overview") {
  qmsDevCurrentId = id;
  qmsDevActiveTab = initialTab;
  const body = document.getElementById("qms-deviations-body");
  body.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading deviation…</div>`;
  try {
    const dev = await qmsFetch(`/qms/deviations/${id}`);
    if (window.PharmaRecent) window.PharmaRecent.recordOpened("deviations", dev.id, dev.title, dev.deviation_number || "");
    body.innerHTML = `
      <div class="qms-page-header">
        <div>
          <button class="btn-secondary" style="margin-bottom:10px;padding:5px 12px;font-size:12px" onclick="qmsDevShowList()">&larr; All Deviations</button>
          <div class="qms-detail-number">${dev.deviation_number} · ${dev.deviation_type} · ${dev.deviation_category}</div>
          <div class="qms-detail-title">${dev.title}</div>
          <div class="qms-detail-meta" id="qms-dev-meta">
            ${qmsDevMetaHTML(dev)}
          </div>
        </div>
        <div class="qms-header-actions">
          <button class="btn-secondary" onclick="qmsDevPrint(${id})">Print</button>
          <button class="btn-secondary" onclick="qmsDevExportDocx(${id})">Export DOCX</button>
        </div>
      </div>
      <div class="qms-body">
        <div class="qms-tabs" id="qms-dev-tabs">
          ${["overview", "lifecycle", "investigation", "impact", "capa", "attachments", "comments", "audit"]
            .map(t => `<button class="qms-tab ${t === qmsDevActiveTab ? "active" : ""}" onclick="qmsDevSwitchTab('${t}')">${qmsDevTabLabel(t)}</button>`).join("")}
        </div>
        <div id="qms-dev-tab-body"></div>
      </div>
    `;
    qmsDevRenderTab(dev);
  } catch (e) {
    if (window.PharmaUI) window.PharmaUI.errorState(body, { message: `Failed to load deviation: ${e.message}`, onRetry: () => qmsDevOpenDetail(id) });
    else body.innerHTML = `<div class="qms-empty"><p>Failed to load deviation: ${e.message}</p></div>`;
  }
}
window.qmsDevOpenDetail = qmsDevOpenDetail;

function qmsDevMetaHTML(dev) {
  return `
    <span>${qmsBadge(dev.status)}</span>
    <span>Department: ${dev.department || "—"}</span>
    <span>Product: ${dev.product || "—"}</span>
    <span>Initiated by: ${dev.initiated_by || "—"}</span>
  `;
}

function qmsDevTabLabel(t) {
  return {
    overview: "Overview", lifecycle: "Lifecycle", investigation: "Investigation Case", impact: "Impact Assessment",
    capa: "CAPA Links", attachments: "Attachments", comments: "Comments", audit: "Audit Trail",
  }[t] || t;
}

async function qmsDevSwitchTab(tab) {
  qmsDevActiveTab = tab;
  const order = ["overview", "lifecycle", "investigation", "impact", "capa", "attachments", "comments", "audit"];
  document.querySelectorAll("#qms-dev-tabs .qms-tab").forEach((b, i) => b.classList.toggle("active", order[i] === tab));
  const dev = await qmsFetch(`/qms/deviations/${qmsDevCurrentId}`);
  qmsDevRenderTab(dev);
}
window.qmsDevSwitchTab = qmsDevSwitchTab;

function qmsDevRenderTab(dev) {
  const el = document.getElementById("qms-dev-tab-body");
  const id = dev.id;

  if (qmsDevActiveTab === "overview") {
    const isDraft = dev.status === "Draft";
    const ro = isDraft ? "" : "disabled";
    el.innerHTML = `
      <div class="qms-section-card">
        <h3>Deviation Details</h3>
        ${isDraft ? "" : `<p style="font-size:12px;color:var(--text-muted);margin-bottom:8px">Read-only — deviation details can only be edited while the deviation is in Draft.</p>`}
        <div class="form-grid">
          <div class="form-field"><label>Area</label><input type="text" id="qms-dov-area" value="${dev.area || ""}" ${ro} /></div>
          <div class="form-field"><label>Product</label><input type="text" id="qms-dov-product" value="${dev.product || ""}" ${ro} /></div>
          <div class="form-field"><label>Batch/Lot</label><input type="text" id="qms-dov-batch" value="${dev.batch_lot || ""}" ${ro} /></div>
          <div class="form-field"><label>Equipment</label><input type="text" id="qms-dov-equipment" value="${dev.equipment || ""}" ${ro} /></div>
          <div class="form-field"><label>Risk Level</label><input type="text" id="qms-dov-risk" value="${dev.risk_level || ""}" ${ro} /></div>
          <div class="form-field span-2"><label>Description</label><textarea id="qms-dov-desc" ${ro}>${dev.description || ""}</textarea></div>
          <div class="form-field span-2"><label>Immediate Action Taken</label><textarea id="qms-dov-action" ${ro}>${dev.immediate_action || ""}</textarea></div>
        </div>
        ${isDraft ? `
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsDevSaveOverview(${id})">Save</button>
        </div>` : ""}
      </div>
    `;
  } else if (qmsDevActiveTab === "lifecycle") {
    qmsDevRenderLifecycleTab(dev);
  } else if (qmsDevActiveTab === "investigation") {
    if (!dev.investigation_unlocked) {
      el.innerHTML = `
        <div class="qms-section-card" style="text-align:center;padding:40px 20px">
          <div style="font-size:32px;margin-bottom:8px">🔒</div>
          <h3>Investigation Case Locked</h3>
          <p style="font-size:12.5px;color:var(--text-muted)">Reason: ${dev.lock_reason || "Waiting for QA Approval"}</p>
          <p style="font-size:12px;color:var(--text-muted);margin-top:8px">
            Complete the pending approval step on the <a href="#" onclick="qmsDevSwitchTab('lifecycle');return false;">Lifecycle</a> tab to unlock this tab.
          </p>
        </div>`;
    } else {
      qmsDevRenderInvestigationCase(id);
    }
  } else if (qmsDevActiveTab === "impact") {
    qmsDevRenderImpact(id);
  } else if (qmsDevActiveTab === "capa") {
    qmsDevRenderCapaLinks(id);
  } else if (qmsDevActiveTab === "attachments") {
    el.innerHTML = `<div id="qms-attachments-deviation-${id}"></div>`;
    qmsRenderAttachments(`qms-attachments-deviation-${id}`, "deviation", id);
  } else if (qmsDevActiveTab === "comments") {
    el.innerHTML = `<div id="qms-comments-deviation-${id}"></div>`;
    qmsRenderComments(`qms-comments-deviation-${id}`, "deviation", id);
  } else if (qmsDevActiveTab === "audit") {
    el.innerHTML = `<div id="qms-audit-deviation-${id}"></div>`;
    qmsRenderAuditTrail(`qms-audit-deviation-${id}`, "deviation", id);
  }
}

async function qmsDevSaveOverview(id) {
  const data = {
    area: document.getElementById("qms-dov-area").value.trim(),
    product: document.getElementById("qms-dov-product").value.trim(),
    batch_lot: document.getElementById("qms-dov-batch").value.trim(),
    equipment: document.getElementById("qms-dov-equipment").value.trim(),
    risk_level: document.getElementById("qms-dov-risk").value.trim(),
    description: document.getElementById("qms-dov-desc").value,
    immediate_action: document.getElementById("qms-dov-action").value,
  };
  try {
    await qmsPutJSON(`/qms/deviations/${id}`, data);
    qmsToast("Saved");
  } catch (e) {
    qmsToast("Save failed: " + e.message);
  }
}
window.qmsDevSaveOverview = qmsDevSaveOverview;

// ── Investigation Case tab: mounts the reusable investigation_case.js component ──
// The Investigation Case (evidence, SOP review, interviews, timeline, AI
// Assistant, root cause, risk, attachments, summary) is a separate concern
// from the Lifecycle/Workflow tab — see investigation_case.js. This module
// only mounts it once unlocked; it owns no investigation UI of its own.

function qmsDevRenderInvestigationCase(id) {
  const el = document.getElementById("qms-dev-tab-body");
  el.innerHTML = `<div id="qms-investigation-case-deviation-${id}"></div>`;
  if (window.InvestigationCase) {
    window.InvestigationCase.mount(`qms-investigation-case-deviation-${id}`, "deviation", id, "/qms/deviations");
  } else {
    el.innerHTML = `<div class="qms-empty"><p>Investigation Case component failed to load.</p></div>`;
  }
}

// ── Impact assessment tab ──────────────────────────────────────────────────────

async function qmsDevRenderImpact(id) {
  const el = document.getElementById("qms-dev-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading impact assessment…</div>`;
  const impacts = await qmsFetch(`/qms/deviations/${id}/impact`);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>AI-Suggested Impact Assessment</h3>
      <button class="btn-secondary" onclick="qmsDevSuggestImpact(${id})"><span class=\'icon\' data-lucide=\'sparkles\'></span> Suggest Impact Areas with AI</button>
      <div id="qms-dev-impact-suggestions" style="margin-top:12px"></div>
    </div>
    <div class="qms-section-card">
      <h3>Add Impact Assessment Entry</h3>
      <div class="form-grid">
        <div class="form-field"><label>Impact Area</label><input type="text" id="qms-impact-area" placeholder="e.g. Product Quality" /></div>
        <div class="form-field"><label>Risk Level</label><input type="text" id="qms-impact-risk" placeholder="Low / Medium / High / Critical" /></div>
        <div class="form-field span-2"><label>Assessment</label><textarea id="qms-impact-text"></textarea></div>
        <div class="form-field span-2"><label>Batches Affected</label><input type="text" id="qms-impact-batches" /></div>
      </div>
      <div class="qms-form-actions">
        <button class="btn-primary" onclick="qmsDevAddImpact(${id})">Add</button>
      </div>
    </div>
    ${impacts.length ? `
      <table class="qms-table">
        <thead><tr><th>Impact Area</th><th>Assessment</th><th>Risk Level</th><th>Batches Affected</th></tr></thead>
        <tbody>${impacts.map(i => `<tr><td>${i.impact_area}</td><td>${i.assessment_text}</td><td>${qmsBadge(i.risk_level)}</td><td>${i.batches_affected || "—"}</td></tr>`).join("")}</tbody>
      </table>` : `<div class="qms-empty"><p>No impact assessment entries yet.</p></div>`}
  `;
}

async function qmsDevSuggestImpact(id) {
  const el = document.getElementById("qms-dev-impact-suggestions");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Generating suggestions…</div>`;
  try {
    const suggestions = await qmsPostJSON(`/qms/deviations/${id}/suggest-impact`, {});
    el.innerHTML = suggestions.length ? suggestions.map(s => `
      <div class="qms-panel-item">
        <div>
          <strong>${s.impact_area}</strong> — ${qmsBadge(s.risk_level)}
          <div>${s.assessment_text}</div>
          <div class="qms-panel-item-meta">Batches: ${s.batches_affected || "—"}</div>
        </div>
        <button class="btn-secondary" style="padding:5px 12px;font-size:11px" onclick='qmsDevAcceptImpactSuggestion(${id}, ${JSON.stringify(s).replace(/'/g, "&apos;")})'>Add to Record</button>
      </div>`).join("") : `<p style="font-size:12.5px;color:var(--text-muted)">No suggestions returned.</p>`;
  } catch (e) {
    el.innerHTML = `<p style="font-size:12.5px;color:var(--text-muted)">Failed: ${e.message}</p>`;
  }
}
window.qmsDevSuggestImpact = qmsDevSuggestImpact;

async function qmsDevAcceptImpactSuggestion(id, suggestion) {
  try {
    await qmsPostJSON(`/qms/deviations/${id}/impact`, suggestion);
    qmsToast("Added to record");
    qmsDevRenderImpact(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDevAcceptImpactSuggestion = qmsDevAcceptImpactSuggestion;

async function qmsDevAddImpact(id) {
  const data = {
    impact_area: document.getElementById("qms-impact-area").value.trim(),
    risk_level: document.getElementById("qms-impact-risk").value.trim(),
    assessment_text: document.getElementById("qms-impact-text").value.trim(),
    batches_affected: document.getElementById("qms-impact-batches").value.trim(),
  };
  if (!data.impact_area) { qmsToast("Impact area is required"); return; }
  try {
    await qmsPostJSON(`/qms/deviations/${id}/impact`, data);
    qmsDevRenderImpact(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDevAddImpact = qmsDevAddImpact;

// ── CAPA links tab ──────────────────────────────────────────────────────────────

async function qmsDevRenderCapaLinks(id) {
  const el = document.getElementById("qms-dev-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading linked CAPAs…</div>`;
  const capas = await qmsFetch(`/qms/deviations/${id}/capas`);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>AI CAPA Suggestion</h3>
      <p style="font-size:12.5px;color:var(--text-muted);margin-bottom:12px">
        Draft problem statement, root cause, and corrective/preventive actions to seed a new CAPA record.
      </p>
      <button class="btn-secondary" onclick="qmsDevSuggestCapa(${id})"><span class=\'icon\' data-lucide=\'sparkles\'></span> Suggest CAPA Content with AI</button>
      <div id="qms-dev-capa-suggestion" style="margin-top:12px"></div>
    </div>
    <div class="qms-section-card">
      <h3>Linked CAPAs</h3>
      ${capas.length ? `
        <table class="qms-table">
          <thead><tr><th>CAPA Number</th><th>Title</th><th>Status</th></tr></thead>
          <tbody>${capas.map(c => `<tr class="clickable" onclick="document.getElementById('nav-qms-capa') && document.getElementById('nav-qms-capa').click()"><td>${c.capa_number}</td><td>${c.title}</td><td>${qmsBadge(c.status)}</td></tr>`).join("")}</tbody>
        </table>` : `<div class="qms-empty"><p>No CAPA linked to this deviation yet.</p></div>`}
    </div>
  `;
}

async function qmsDevSuggestCapa(id) {
  const el = document.getElementById("qms-dev-capa-suggestion");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Generating CAPA suggestion…</div>`;
  try {
    const s = await qmsPostJSON(`/qms/deviations/${id}/suggest-capa`, {});
    window._qmsDevLastCapaSuggestion = s;
    el.innerHTML = `
      <div class="qms-panel-item" style="flex-direction:column;align-items:stretch">
        <div><strong>Problem Statement:</strong> ${s.problem_statement || ""}</div>
        <div><strong>Root Cause:</strong> ${s.root_cause || ""}</div>
        <div><strong>Corrective Actions:</strong> ${(s.corrective_actions || []).map(a => a.description).join("; ")}</div>
        <div><strong>Preventive Actions:</strong> ${(s.preventive_actions || []).map(a => a.description).join("; ")}</div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsDevCreateCapaFromSuggestion(${id})">Create CAPA from this Suggestion</button>
        </div>
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<p style="font-size:12.5px;color:var(--text-muted)">Failed: ${e.message}</p>`;
  }
}
window.qmsDevSuggestCapa = qmsDevSuggestCapa;

async function qmsDevCreateCapaFromSuggestion(id) {
  const s = window._qmsDevLastCapaSuggestion;
  const dev = await qmsFetch(`/qms/deviations/${id}`);
  if (!s) return;
  try {
    const capa = await qmsPostJSON("/qms/capa", {
      title: `CAPA for ${dev.deviation_number}`,
      capa_source: "Deviation",
      source_reference: dev.deviation_number,
      department: dev.department,
      problem_statement: s.problem_statement || "",
      root_cause: s.root_cause || "",
    });
    for (const a of (s.corrective_actions || [])) {
      await qmsPostJSON(`/qms/capa/${capa.id}/actions`, { action_type: "Corrective", description: a.description, owner: a.owner || "" });
    }
    for (const a of (s.preventive_actions || [])) {
      await qmsPostJSON(`/qms/capa/${capa.id}/actions`, { action_type: "Preventive", description: a.description, owner: a.owner || "" });
    }
    await qmsPostJSON(`/qms/deviations/${id}/link-capa`, { capa_id: capa.id });
    qmsToast(`Created and linked ${capa.capa_number}`);
    qmsDevRenderCapaLinks(id);
  } catch (e) {
    qmsToast("Failed to create CAPA: " + e.message);
  }
}
window.qmsDevCreateCapaFromSuggestion = qmsDevCreateCapaFromSuggestion;

// ── Workflow tab: gated, named-approver investigation lifecycle ──────────────
// Replaces the old free action-dropdown approval tab. Buttons shown here are
// context-sensitive: only the current step is actionable, and only for the
// user actually entitled to act on it (a named approver for an 'approval'
// step, or any user whose role is eligible for an 'activity' step) — see
// services/workflow_engine.py::decide_step for the server-side enforcement
// this UI mirrors.

const QMS_DEV_STEP_BUTTON_LABELS = {
  evidence_collection: "Investigation Complete — Submit for CAPA Review",  // step_key kept from V1 for engine compat; displays as "Investigation"
  effectiveness_check: "Mark Effectiveness Check Complete",
  closed: "Close Deviation",
};

// High-level lifecycle shown in the Lifecycle tab (architecture refactor
// §2/§10) — "Review" and "CAPA" each group several individual approval
// steps (unchanged from the underlying workflow) under one phase label.
const QMS_DEV_LIFECYCLE_PHASES = ["Draft", "Submitted", "Review", "Investigation", "CAPA", "Effectiveness Check", "Closure"];

let qmsDevBuilderSteps = [];
let qmsDevBuilderCapaPhase = {};

async function qmsDevRenderLifecycleTab(dev) {
  const id = dev.id;
  const el = document.getElementById("qms-dev-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading lifecycle…</div>`;
  let wf;
  try {
    wf = await qmsFetch(`/qms/deviations/${id}/workflow`);
  } catch (e) {
    el.innerHTML = `<div class="qms-empty"><p>Failed to load lifecycle: ${e.message}</p></div>`;
    return;
  }

  if (!wf.instance) {
    qmsDevBuilderSaving = false;
    try {
      const builder = await qmsFetch(`/qms/deviations/${id}/workflow-builder`);
      qmsDevBuilderSteps = builder.steps;
      qmsDevBuilderCapaPhase = builder.capa_phase;
    } catch (e) {
      el.innerHTML = `<div class="qms-empty"><p>Failed to load workflow builder: ${e.message}</p></div>`;
      return;
    }
    qmsDevRenderWorkflowBuilder(id);
    return;
  }

  const user = (window.PharmaAuth && window.PharmaAuth.getUser()) || {};
  const currentPhase = wf.current_phase || "Draft";

  // Group steps by phase, preserving step_order within each phase.
  const stepsByPhase = {};
  for (const s of wf.steps) {
    (stepsByPhase[s.phase] = stepsByPhase[s.phase] || []).push(s);
  }

  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Lifecycle</h3>
      <div class="qms-lifecycle-track">
        ${QMS_DEV_LIFECYCLE_PHASES.map(p => `
          <span class="qms-lifecycle-phase ${p === currentPhase ? "active" : ""} ${QMS_DEV_LIFECYCLE_PHASES.indexOf(p) < QMS_DEV_LIFECYCLE_PHASES.indexOf(currentPhase) ? "done" : ""}">${p}</span>
        `).join("<span class=\"qms-lifecycle-arrow\">→</span>")}
      </div>
      <div class="qms-detail-meta" style="margin-top:12px">
        <span>Progress: ${wf.progress_pct}%</span>
        <span>Assigned To: ${(wf.assigned_to || []).join(", ") || "—"}</span>
        <span>Pending Since: ${wf.pending_since ? new Date(wf.pending_since).toLocaleDateString() : "—"}</span>
        <span>Remaining Steps: ${wf.remaining_steps.length}</span>
      </div>
    </div>

    ${QMS_DEV_LIFECYCLE_PHASES.filter(p => stepsByPhase[p]).map(phase => {
      const steps = stepsByPhase[phase];
      const completed = steps.filter(s => s.status === "approved").length;
      const header = steps.length > 1 ? `${phase} (${completed} of ${steps.length} Complete)` : phase;
      return `
        <div class="qms-section-card">
          <h3>${header}</h3>
          <div class="qms-workflow-stepper">
            ${steps.map(s => qmsDevWorkflowStepHTML(id, s, wf.instance, user)).join("")}
          </div>
        </div>
      `;
    }).join("")}
  `;
}
window.qmsDevRenderLifecycleTab = qmsDevRenderLifecycleTab;

// ── Workflow Builder: Draft-time, whole-lifecycle approver configuration ─────
// Two parts, both saved together (routes/qms_deviations.py::update_workflow_builder):
//   qmsDevBuilderSteps     — the dynamic Review chain. The initiator adds/
//                            removes/reorders steps and picks a Department +
//                            Approver for each. QA Approval (the last row) is
//                            always present, always final, and cannot be
//                            removed or reordered.
//   qmsDevBuilderCapaPhase — the two fixed, single-approver CAPA-phase steps
//                            (QA Review, Final Approval) that follow
//                            Investigation; not reorderable/addable/removable.
// This is the only place approvers are configured for a deviation — there is
// no runtime "Assign Approver" action anywhere in the Lifecycle tab.

// True while a workflow-builder PUT is in flight. Every mutating action
// below checks this before touching qmsDevBuilderSteps/the DOM, and the
// render function disables every builder control while it's true — without
// this, two mutations fired before the first one's response/re-render
// lands (e.g. a fast double-click) would both call qmsDevBuilderSyncFromDOM()
// against the same stale, not-yet-re-rendered DOM, and whichever PUT's
// response arrived last would silently clobber the other's change.
let qmsDevBuilderSaving = false;

function qmsDevRenderWorkflowBuilder(id) {
  const el = document.getElementById("qms-dev-tab-body");
  const lastIdx = qmsDevBuilderSteps.length - 1;
  const busy = qmsDevBuilderSaving ? "disabled" : "";
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Workflow Builder</h3>
      <p style="font-size:12.5px;color:var(--text-muted);margin-bottom:12px">
        This deviation has not been submitted yet. Configure every approver for its full lifecycle here —
        there is no assignment step after submission. Review chain: add, remove, and reorder steps, and
        choose a Department and Approver for each; QA Approval is mandatory and always the final step, and
        the Investigation Case stays locked until it clears.
      </p>
      <div id="qms-wfb-steps">
        ${qmsDevBuilderSteps.map((s, i) => qmsDevBuilderStepHTML(s, i, i === lastIdx, busy)).join("")}
      </div>
      <div class="qms-form-actions" style="margin-top:10px">
        <button class="btn-secondary" onclick="qmsDevBuilderAddStep(${id})" ${busy}>+ Add Step</button>
      </div>
    </div>
    <div class="qms-section-card">
      <h3>CAPA Phase Approvers</h3>
      <p style="font-size:12.5px;color:var(--text-muted);margin-bottom:12px">
        QA Review and Final Approval follow the Investigation Case and are always present — pick their
        approver here so they're already assigned when the record reaches CAPA.
      </p>
      ${qmsDevBuilderCapaPhaseHTML(busy)}
    </div>
    <div class="qms-section-card">
      <div class="qms-form-actions">
        <button class="btn-secondary" onclick="qmsDevBuilderSave(${id})" ${busy}>Save Workflow</button>
        <button class="btn-primary" onclick="qmsDevSubmitForReview(${id})" ${busy}>Submit for Review</button>
      </div>
    </div>
  `;
}
window.qmsDevRenderWorkflowBuilder = qmsDevRenderWorkflowBuilder;

function qmsDevBuilderCapaPhaseHTML(busy) {
  const c = qmsDevBuilderCapaPhase || {};
  return `
    <div class="qms-stat-card" style="margin-bottom:10px">
      <strong>QA Review</strong>
      <div class="form-grid">
        <div class="form-field"><label>Approver User ID</label><input type="text" id="qms-wfb-capa-qa-review-uid" value="${c.qa_review_approver_user_id || ""}" placeholder="Supabase user id" ${busy} /></div>
        <div class="form-field"><label>Approver Display Name</label><input type="text" id="qms-wfb-capa-qa-review-dname" value="${c.qa_review_approver_display_name || ""}" placeholder="Full name" ${busy} /></div>
      </div>
    </div>
    <div class="qms-stat-card">
      <strong>Final Approval</strong>
      <div class="form-grid">
        <div class="form-field"><label>Approver User ID</label><input type="text" id="qms-wfb-capa-final-uid" value="${c.final_approval_approver_user_id || ""}" placeholder="Supabase user id" ${busy} /></div>
        <div class="form-field"><label>Approver Display Name</label><input type="text" id="qms-wfb-capa-final-dname" value="${c.final_approval_approver_display_name || ""}" placeholder="Full name" ${busy} /></div>
      </div>
    </div>
  `;
}

function qmsDevBuilderStepHTML(step, i, isFinal, busy) {
  return `
    <div class="qms-stat-card ${isFinal ? "info" : ""}" style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <strong>${i + 2}. ${isFinal ? "QA Approval (mandatory, final)" : `Review Step ${i + 2}`}</strong>
        <div>
          <button class="btn-secondary" style="padding:3px 8px;font-size:11px" onclick="qmsDevBuilderMoveStep(${i}, -1)" ${isFinal || i === 0 ? "disabled" : busy}>&uarr;</button>
          <button class="btn-secondary" style="padding:3px 8px;font-size:11px" onclick="qmsDevBuilderMoveStep(${i}, 1)" ${isFinal || i >= qmsDevBuilderSteps.length - 2 ? "disabled" : busy}>&darr;</button>
          <button class="btn-secondary" style="padding:3px 8px;font-size:11px" onclick="qmsDevBuilderRemoveStep(${i})" ${isFinal ? "disabled" : busy}>Remove</button>
        </div>
      </div>
      <div class="form-grid">
        <div class="form-field"><label>Step Name</label><input type="text" id="qms-wfb-name-${i}" value="${step.step_name || ""}" ${isFinal ? "disabled" : busy} /></div>
        <div class="form-field"><label>Department</label><input type="text" id="qms-wfb-dept-${i}" value="${step.department || ""}" placeholder="e.g. Production, QA, Engineering, Warehouse" ${busy} /></div>
        <div class="form-field"><label>Approver User ID</label><input type="text" id="qms-wfb-uid-${i}" value="${step.approver_user_id || ""}" placeholder="Supabase user id" ${busy} /></div>
        <div class="form-field"><label>Approver Display Name</label><input type="text" id="qms-wfb-dname-${i}" value="${step.approver_display_name || ""}" placeholder="Full name" ${busy} /></div>
      </div>
    </div>
  `;
}

function qmsDevBuilderSyncFromDOM() {
  qmsDevBuilderSteps = qmsDevBuilderSteps.map((s, i) => ({
    ...s,
    step_name: (document.getElementById(`qms-wfb-name-${i}`) || { value: s.step_name || "" }).value.trim(),
    department: (document.getElementById(`qms-wfb-dept-${i}`) || { value: "" }).value.trim(),
    approver_user_id: (document.getElementById(`qms-wfb-uid-${i}`) || { value: "" }).value.trim(),
    approver_display_name: (document.getElementById(`qms-wfb-dname-${i}`) || { value: "" }).value.trim(),
  }));
  qmsDevBuilderCapaPhase = {
    qa_review_approver_user_id: (document.getElementById("qms-wfb-capa-qa-review-uid") || { value: "" }).value.trim(),
    qa_review_approver_display_name: (document.getElementById("qms-wfb-capa-qa-review-dname") || { value: "" }).value.trim(),
    final_approval_approver_user_id: (document.getElementById("qms-wfb-capa-final-uid") || { value: "" }).value.trim(),
    final_approval_approver_display_name: (document.getElementById("qms-wfb-capa-final-dname") || { value: "" }).value.trim(),
  };
}

// Every structural edit (add/remove/reorder) persists immediately via PUT —
// not just the explicit "Save Workflow" button — so switching tabs or
// reloading mid-edit can never silently drop a step. qmsDevBuilderSteps is
// always replaced with the server's response (canonical step_order/ids),
// never trusted from the client-side splice/swap alone. Serialized by
// qmsDevBuilderSaving (see above) so overlapping mutations can't race.
async function qmsDevBuilderPersist(id, { toast } = {}) {
  qmsDevBuilderSaving = true;
  qmsDevRenderWorkflowBuilder(id);
  try {
    const builder = await qmsPutJSON(`/qms/deviations/${id}/workflow-builder`, {
      steps: qmsDevBuilderSteps, capa_phase: qmsDevBuilderCapaPhase,
    });
    qmsDevBuilderSteps = builder.steps;
    qmsDevBuilderCapaPhase = builder.capa_phase;
    if (toast) qmsToast(toast);
  } catch (e) {
    qmsToast("Failed to save workflow: " + e.message);
  } finally {
    qmsDevBuilderSaving = false;
    qmsDevRenderWorkflowBuilder(id);
  }
}

function qmsDevBuilderAddStep(id) {
  if (qmsDevBuilderSaving) return;
  qmsDevBuilderSyncFromDOM();
  qmsDevBuilderSteps.splice(qmsDevBuilderSteps.length - 1, 0, {
    step_name: "", department: "", approver_user_id: "", approver_display_name: "",
  });
  qmsDevBuilderPersist(id);
}
window.qmsDevBuilderAddStep = qmsDevBuilderAddStep;

function qmsDevBuilderRemoveStep(i) {
  if (qmsDevBuilderSaving) return;
  qmsDevBuilderSyncFromDOM();
  if (i === qmsDevBuilderSteps.length - 1 || qmsDevBuilderSteps.length <= 1) return;
  qmsDevBuilderSteps.splice(i, 1);
  qmsDevBuilderPersist(qmsDevCurrentId);
}
window.qmsDevBuilderRemoveStep = qmsDevBuilderRemoveStep;

function qmsDevBuilderMoveStep(i, dir) {
  if (qmsDevBuilderSaving) return;
  qmsDevBuilderSyncFromDOM();
  const j = i + dir;
  const lastIdx = qmsDevBuilderSteps.length - 1;
  if (j < 0 || j >= lastIdx || i >= lastIdx) return; // never move the final QA Approval row, never move past it
  [qmsDevBuilderSteps[i], qmsDevBuilderSteps[j]] = [qmsDevBuilderSteps[j], qmsDevBuilderSteps[i]];
  qmsDevBuilderPersist(qmsDevCurrentId);
}
window.qmsDevBuilderMoveStep = qmsDevBuilderMoveStep;

function qmsDevBuilderSave(id) {
  if (qmsDevBuilderSaving) return;
  qmsDevBuilderSyncFromDOM();
  return qmsDevBuilderPersist(id, { toast: "Workflow saved" });
}
window.qmsDevBuilderSave = qmsDevBuilderSave;

function qmsDevWorkflowStepHTML(id, step, instance, user) {
  const isCurrent = instance.status === "in_progress" && step.step_order === instance.current_step_order;
  const isPast = step.step_order < instance.current_step_order || step.status !== "pending";
  const stateClass = step.status === "approved" ? "success" : step.status === "rejected" ? "critical"
    : step.status === "returned" ? "warning" : isCurrent ? "info" : "";

  let body = "";
  if (step.status !== "pending") {
    body = `<div class="qms-panel-item-meta">${qmsBadge(step.status)} by ${step.decided_by || "—"} on ${step.decided_at || "—"}${step.comments ? ` — "${step.comments}"` : ""}</div>`;
  } else if (isCurrent) {
    body = qmsDevWorkflowActionHTML(id, step, user);
  } else {
    body = `<div class="qms-panel-item-meta">Not yet reached</div>`;
  }

  return `
    <div class="qms-stat-card ${stateClass}" style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong>${step.step_order}. ${step.step_name}</strong>
        ${step.step_type === "approval" ? qmsDevApproversBadge(step.approvers) : ""}
      </div>
      ${body}
    </div>
  `;
}

function qmsDevApproversBadge(approvers) {
  if (!approvers || !approvers.length) return `<span class="qms-panel-item-meta">No approver assigned</span>`;
  return `<span class="qms-panel-item-meta">Approver(s): ${approvers.map(a => a.display_name || a.user_id).join(", ")}</span>`;
}

function qmsDevWorkflowActionHTML(id, step, user) {
  const formId = `qms-wf-action-${id}-${step.step_order}`;
  if (step.step_type === "approval") {
    const approvers = step.approvers || [];
    if (!approvers.length) {
      // Every step's approver is configured in the Workflow Builder and
      // assigned automatically at Submit for Review (routes/qms_deviations.py
      // ::start_workflow) — an approval step with no approver here means the
      // record predates that guarantee or the workflow is misconfigured.
      // There is no runtime "Assign Approver" control; this must be fixed by
      // re-running the Workflow Builder before submission, not from here.
      return `<div class="qms-panel-item-meta">No approver assigned for this step — the Workflow Builder should have assigned one at submission. Contact your administrator.</div>`;
    }
    const isApprover = approvers.some(a => a.user_id === user.user_id);
    if (!isApprover) {
      return `<div class="qms-panel-item-meta">Waiting for ${approvers.map(a => a.display_name || a.user_id).join(" or ")} to decide.</div>`;
    }
    const safeStepName = String(step.step_name || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    return `
      <div class="form-field" style="margin-top:8px"><label>Comments</label><input type="text" id="${formId}-comments" placeholder="Optional comments" /></div>
      <div class="qms-form-actions">
        <button class="btn-primary" onclick="qmsDevDecide(${id}, ${step.step_order}, 'approve', '${formId}')">Approve</button>
        <button class="btn-secondary" onclick="qmsDevDecide(${id}, ${step.step_order}, 'reject', '${formId}')">Reject</button>
        ${step.step_key === "qa_review" ? `<button class="btn-secondary" onclick="qmsDevDecide(${id}, ${step.step_order}, 'return', '${formId}')">Return for Investigation</button>` : ""}
        <button class="btn-secondary" onclick="qmsDevRequestInfo(${id}, '${safeStepName}')">Request Information</button>
      </div>
    `;
  }

  // activity step
  if (!user.role || !(step.eligible_roles || "").split(",").includes(user.role)) {
    return `<div class="qms-panel-item-meta">Waiting for a user with an eligible role to advance this step.</div>`;
  }
  const label = QMS_DEV_STEP_BUTTON_LABELS[step.step_key] || `Complete "${step.step_name}"`;
  return `
    <div class="qms-form-actions" style="margin-top:8px">
      <button class="btn-primary" onclick="qmsDevDecide(${id}, ${step.step_order}, 'advance', null)">${label}</button>
    </div>
  `;
}

async function qmsDevRefreshCurrentView(id) {
  const dev = await qmsFetch(`/qms/deviations/${id}`);
  const metaEl = document.getElementById("qms-dev-meta");
  if (metaEl) metaEl.innerHTML = qmsDevMetaHTML(dev);
  qmsDevRenderTab(dev);
}

async function qmsDevSubmitForReview(id) {
  if (qmsDevBuilderSaving) return;
  qmsDevBuilderSaving = true;
  qmsDevRenderWorkflowBuilder(id);
  try {
    qmsDevBuilderSyncFromDOM();
    await qmsPutJSON(`/qms/deviations/${id}/workflow-builder`, { steps: qmsDevBuilderSteps, capa_phase: qmsDevBuilderCapaPhase });
    await qmsPostJSON(`/qms/deviations/${id}/workflow/start`, {});
    qmsToast("Submitted for review");
    qmsDevRefreshCurrentView(id);
  } catch (e) {
    qmsToast("Failed to submit: " + e.message);
    qmsDevBuilderSaving = false;
    qmsDevRenderWorkflowBuilder(id);
  }
}
window.qmsDevSubmitForReview = qmsDevSubmitForReview;

async function qmsDevRequestInfo(id, stepName) {
  const text = window.prompt(`Request information for "${stepName}" — what's needed?`);
  if (!text || !text.trim()) return;
  try {
    await qmsPostJSON(`/qms/deviation/${id}/comments`, { comment: `[Request Information — ${stepName}] ${text.trim()}` });
    qmsToast("Information request added as a comment");
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDevRequestInfo = qmsDevRequestInfo;

async function qmsDevDecide(id, stepOrder, decision, formId) {
  const comments = formId && document.getElementById(`${formId}-comments`) ? document.getElementById(`${formId}-comments`).value.trim() : "";
  try {
    await qmsPostJSON(`/qms/deviations/${id}/workflow/steps/${stepOrder}/decide`, { decision, comments });
    qmsToast("Recorded");
    qmsDevRefreshCurrentView(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsDevDecide = qmsDevDecide;

// ── Print / Export ──────────────────────────────────────────────────────────

async function qmsDevPrint(id) {
  try {
    const { markdown, title } = await qmsFetch(`/qms/deviations/${id}/report`);
    const win = window.open("", "_blank");
    win.document.write(`<html><head><title>${title}</title></head><body>${window.marked ? marked.parse(markdown) : `<pre>${markdown}</pre>`}</body></html>`);
    win.document.close();
    win.print();
  } catch (e) {
    qmsToast("Failed to prepare print view: " + e.message);
  }
}
window.qmsDevPrint = qmsDevPrint;

async function qmsDevExportDocx(id) {
  try {
    const res = await fetch(`/qms/deviations/${id}/export/docx`, { method: "POST" });
    if (!res.ok) { qmsToast("Export failed"); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `Deviation_${id}.docx`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    qmsToast("Export error: " + e.message);
  }
}
window.qmsDevExportDocx = qmsDevExportDocx;
