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
          <div class="qms-empty-icon">⚡</div>
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
    container.innerHTML = `<div class="qms-empty"><p>Failed to load deviations: ${e.message}</p></div>`;
  }
}

// ── Create wizard ───────────────────────────────────────────────────────────

function qmsDevOpenNew() {
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
        <button class="btn-primary" onclick="qmsDevCreate()">Create Deviation</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}
window.qmsDevOpenNew = qmsDevOpenNew;

async function qmsDevCreate() {
  const title = document.getElementById("qms-new-dev-title").value.trim();
  if (!title) { qmsToast("Title is required"); return; }
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
    qmsDevOpenDetail(dev.id);
  } catch (e) {
    qmsToast("Failed to create deviation: " + e.message);
  }
}
window.qmsDevCreate = qmsDevCreate;

// ── Detail view ─────────────────────────────────────────────────────────────

async function qmsDevOpenDetail(id) {
  qmsDevCurrentId = id;
  qmsDevActiveTab = "overview";
  const body = document.getElementById("qms-deviations-body");
  body.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading deviation…</div>`;
  try {
    const dev = await qmsFetch(`/qms/deviations/${id}`);
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
          ${["overview", "investigation", "impact", "capa", "attachments", "comments", "audit", "approval"]
            .map(t => `<button class="qms-tab ${t === qmsDevActiveTab ? "active" : ""}" onclick="qmsDevSwitchTab('${t}')">${qmsDevTabLabel(t)}</button>`).join("")}
        </div>
        <div id="qms-dev-tab-body"></div>
      </div>
    `;
    qmsDevRenderTab(dev);
  } catch (e) {
    body.innerHTML = `<div class="qms-empty"><p>Failed to load deviation: ${e.message}</p></div>`;
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
    overview: "Overview", investigation: "Investigation", impact: "Impact Assessment",
    capa: "CAPA Links", attachments: "Attachments", comments: "Comments",
    audit: "Audit Trail", approval: "Approval",
  }[t] || t;
}

async function qmsDevSwitchTab(tab) {
  qmsDevActiveTab = tab;
  const order = ["overview", "investigation", "impact", "capa", "attachments", "comments", "audit", "approval"];
  document.querySelectorAll("#qms-dev-tabs .qms-tab").forEach((b, i) => b.classList.toggle("active", order[i] === tab));
  const dev = await qmsFetch(`/qms/deviations/${qmsDevCurrentId}`);
  qmsDevRenderTab(dev);
}
window.qmsDevSwitchTab = qmsDevSwitchTab;

function qmsDevRenderTab(dev) {
  const el = document.getElementById("qms-dev-tab-body");
  const id = dev.id;

  if (qmsDevActiveTab === "overview") {
    el.innerHTML = `
      <div class="qms-section-card">
        <h3>Deviation Details</h3>
        <div class="form-grid">
          <div class="form-field"><label>Area</label><input type="text" id="qms-dov-area" value="${dev.area || ""}" /></div>
          <div class="form-field"><label>Product</label><input type="text" id="qms-dov-product" value="${dev.product || ""}" /></div>
          <div class="form-field"><label>Batch/Lot</label><input type="text" id="qms-dov-batch" value="${dev.batch_lot || ""}" /></div>
          <div class="form-field"><label>Equipment</label><input type="text" id="qms-dov-equipment" value="${dev.equipment || ""}" /></div>
          <div class="form-field"><label>Risk Level</label><input type="text" id="qms-dov-risk" value="${dev.risk_level || ""}" /></div>
          <div class="form-field"><label>QA Reviewer</label><input type="text" id="qms-dov-qa" value="${dev.qa_reviewer || ""}" /></div>
          <div class="form-field span-2"><label>Description</label><textarea id="qms-dov-desc">${dev.description || ""}</textarea></div>
          <div class="form-field span-2"><label>Immediate Action Taken</label><textarea id="qms-dov-action">${dev.immediate_action || ""}</textarea></div>
        </div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsDevSaveOverview(${id})">Save</button>
        </div>
      </div>
    `;
  } else if (qmsDevActiveTab === "investigation") {
    qmsDevRenderInvestigation(id);
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
  } else if (qmsDevActiveTab === "approval") {
    el.innerHTML = `<div id="qms-approval-deviation-${id}"></div>`;
    qmsDevRenderApprovalTab(id);
  }
}

async function qmsDevSaveOverview(id) {
  const data = {
    area: document.getElementById("qms-dov-area").value.trim(),
    product: document.getElementById("qms-dov-product").value.trim(),
    batch_lot: document.getElementById("qms-dov-batch").value.trim(),
    equipment: document.getElementById("qms-dov-equipment").value.trim(),
    risk_level: document.getElementById("qms-dov-risk").value.trim(),
    qa_reviewer: document.getElementById("qms-dov-qa").value.trim(),
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

// ── Investigation tab: AI Investigation Assistant ─────────────────────────────

async function qmsDevRenderInvestigation(id) {
  const el = document.getElementById("qms-dev-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading investigation…</div>`;
  const inv = await qmsFetch(`/qms/deviations/${id}/investigation`);
  const fb = (inv && inv.fishbone_data) || {};
  const fw = (inv && inv.five_why_data) || [];
  const tl = (inv && inv.timeline_data) || [];

  el.innerHTML = `
    <div class="qms-section-card">
      <h3>AI Investigation Assistant</h3>
      <p style="font-size:12.5px;color:var(--text-muted);margin-bottom:12px">
        Generates a Fishbone (Ishikawa) analysis, 5-Why chain, investigation timeline, and root cause
        determination using the PharmaGPT regulatory persona.
      </p>
      <button class="btn-primary" id="qms-dev-investigate-btn" onclick="qmsDevRunInvestigation(${id})">✨ Run AI Investigation</button>
    </div>

    ${(inv && inv.root_cause_statement) ? `
      <div class="qms-section-card">
        <h3>Root Cause Determination</h3>
        <div class="form-grid">
          <div class="form-field"><label>Category</label><input type="text" id="qms-inv-rc-category" value="${inv.root_cause_category || ""}" /></div>
          <div class="form-field span-2"><label>Root Cause Statement</label><textarea id="qms-inv-rc-statement">${inv.root_cause_statement || ""}</textarea></div>
        </div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsDevSaveRootCause(${id})">Save</button>
        </div>
      </div>

      <div class="qms-section-card">
        <h3>Fishbone (Ishikawa) Analysis</h3>
        <div class="form-grid cols-3">
          ${["man", "machine", "method", "material", "measurement", "environment"].map(cat => `
            <div class="form-field">
              <label>${cat}</label>
              <div style="font-size:12.5px">${(fb[cat] || []).length ? "<ul style='margin:0;padding-left:16px'>" + fb[cat].map(i => `<li>${i}</li>`).join("") + "</ul>" : "<em>None identified</em>"}</div>
            </div>
          `).join("")}
        </div>
      </div>

      <div class="qms-section-card">
        <h3>Five-Why Analysis</h3>
        ${fw.length ? `
          <table class="qms-table">
            <thead><tr><th style="width:60px">#</th><th>Question</th><th>Answer</th></tr></thead>
            <tbody>${fw.map((w, i) => `<tr><td>Why ${i + 1}</td><td>${w.question || ""}</td><td>${w.answer || ""}</td></tr>`).join("")}</tbody>
          </table>` : `<p style="font-size:12.5px;color:var(--text-muted)">No 5-Why analysis recorded.</p>`}
      </div>

      <div class="qms-section-card">
        <h3>Timeline</h3>
        ${tl.length ? `
          <table class="qms-table">
            <thead><tr><th>Date/Time</th><th>Event</th></tr></thead>
            <tbody>${tl.map(t => `<tr><td>${t.datetime || ""}</td><td>${t.event || ""}</td></tr>`).join("")}</tbody>
          </table>` : `<p style="font-size:12.5px;color:var(--text-muted)">No timeline recorded.</p>`}
      </div>
    ` : ""}
  `;
}

async function qmsDevRunInvestigation(id) {
  const btn = document.getElementById("qms-dev-investigate-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Running AI investigation…"; }
  qmsToast("Running AI Investigation Assistant…");
  try {
    await qmsPostJSON(`/qms/deviations/${id}/investigate`, {});
    qmsToast("Investigation complete");
    qmsDevRenderInvestigation(id);
  } catch (e) {
    qmsToast("Investigation failed: " + e.message);
    if (btn) { btn.disabled = false; btn.textContent = "✨ Run AI Investigation"; }
  }
}
window.qmsDevRunInvestigation = qmsDevRunInvestigation;

async function qmsDevSaveRootCause(id) {
  const data = {
    root_cause_category: document.getElementById("qms-inv-rc-category").value.trim(),
    root_cause_statement: document.getElementById("qms-inv-rc-statement").value.trim(),
  };
  try {
    await qmsPutJSON(`/qms/deviations/${id}/investigation`, data);
    qmsToast("Root cause saved");
  } catch (e) {
    qmsToast("Save failed: " + e.message);
  }
}
window.qmsDevSaveRootCause = qmsDevSaveRootCause;

// ── Impact assessment tab ──────────────────────────────────────────────────────

async function qmsDevRenderImpact(id) {
  const el = document.getElementById("qms-dev-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading impact assessment…</div>`;
  const impacts = await qmsFetch(`/qms/deviations/${id}/impact`);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>AI-Suggested Impact Assessment</h3>
      <button class="btn-secondary" onclick="qmsDevSuggestImpact(${id})">✨ Suggest Impact Areas with AI</button>
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
      <button class="btn-secondary" onclick="qmsDevSuggestCapa(${id})">✨ Suggest CAPA Content with AI</button>
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

// ── Approval / status transition ──────────────────────────────────────────────

async function qmsDevRenderApprovalTab(id) {
  const actions = [
    "Investigation Started", "Root Cause Identified", "Impact Assessed", "Risk Assessed",
    "CAPA Assigned", "Submitted for QA Review", "Approved", "Rejected", "Closed",
  ];
  qmsRenderApproval(`qms-approval-deviation-${id}`, "deviation", id, actions, `/qms/deviations/${id}/approval`,
    () => qmsDevRefreshApprovalTab(id));
}

async function qmsDevRefreshApprovalTab(id) {
  const dev = await qmsFetch(`/qms/deviations/${id}`);
  const metaEl = document.getElementById("qms-dev-meta");
  if (metaEl) metaEl.innerHTML = qmsDevMetaHTML(dev);
  qmsDevRenderApprovalTab(id);
}

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
