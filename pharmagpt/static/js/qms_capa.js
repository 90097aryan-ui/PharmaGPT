/*
 * qms_capa.js — CAPA (Corrective and Preventive Action) module frontend.
 *
 * Renders entirely into <main id="view-qms-capa"><div id="qms-capa-body">.
 * Follows the same structure as qms_documents.js / qms_deviations.js.
 */

let qmsCapaCurrentId = null;
let qmsCapaActiveTab = "overview";

function initQMSCapa() {
  qmsLoadMeta().then(() => qmsCapaShowList());
}
window.initQMSCapa = initQMSCapa;

// ── List view ───────────────────────────────────────────────────────────────

async function qmsCapaShowList(filters = {}) {
  qmsCapaCurrentId = null;
  const body = document.getElementById("qms-capa-body");
  body.innerHTML = `
    <div class="qms-page-header">
      <div>
        <h2>CAPA — Corrective &amp; Preventive Action</h2>
        <p>Actions, owners, due dates, escalation, and effectiveness checks</p>
      </div>
      <div class="qms-header-actions">
        <button class="btn-primary" onclick="qmsCapaOpenNew()">+ New CAPA</button>
      </div>
    </div>
    <div class="qms-body">
      <div id="qms-capa-toolbar"></div>
      <div id="qms-capa-list-container"><div class="qms-loading"><div class="qms-spinner"></div> Loading CAPAs…</div></div>
    </div>
  `;
  renderQMSCapaToolbar(filters);
  await qmsCapaLoadList(filters);
}
window.qmsCapaShowList = qmsCapaShowList;

function renderQMSCapaToolbar(filters) {
  const meta = window.QMS_META || { capa_sources: [], capa_statuses: [] };
  const el = document.getElementById("qms-capa-toolbar");
  el.innerHTML = `
    <div class="qms-toolbar">
      <input type="text" id="qms-capa-search" placeholder="Search by title, number, or problem statement…" value="${filters.q || ""}" />
      <select id="qms-capa-filter-source">
        <option value="">All Sources</option>
        ${qmsOptions(meta.capa_sources, filters.source)}
      </select>
      <select id="qms-capa-filter-status">
        <option value="">All Statuses</option>
        ${qmsOptions(meta.capa_statuses, filters.status)}
      </select>
      <button class="btn-secondary" onclick="qmsCapaApplyFilters()">Filter</button>
    </div>
  `;
  document.getElementById("qms-capa-search").addEventListener("keydown", e => {
    if (e.key === "Enter") qmsCapaApplyFilters();
  });
}

function qmsCapaApplyFilters() {
  const filters = {
    q: document.getElementById("qms-capa-search").value.trim(),
    source: document.getElementById("qms-capa-filter-source").value,
    status: document.getElementById("qms-capa-filter-status").value,
  };
  qmsCapaLoadList(filters);
}
window.qmsCapaApplyFilters = qmsCapaApplyFilters;

async function qmsCapaLoadList(filters = {}) {
  const container = document.getElementById("qms-capa-list-container");
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.source) params.set("source", filters.source);
  if (filters.status) params.set("status", filters.status);

  try {
    const capas = await qmsFetch(`/qms/capa?${params.toString()}`);
    if (!capas.length) {
      container.innerHTML = `
        <div class="qms-empty">
          <div class="qms-empty-icon"><span class=\'icon\' data-lucide=\'repeat\'></span></div>
          <h3>No CAPAs yet</h3>
          <p>Create your first CAPA, or raise one from a Deviation's "CAPA Links" tab.</p>
        </div>`;
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    container.innerHTML = `
      <table class="qms-table">
        <thead><tr><th>CAPA Number</th><th>Title</th><th>Source</th><th>Department</th><th>Status</th><th>Target Closure</th></tr></thead>
        <tbody>
          ${capas.map(c => {
            const overdue = c.status !== "Closed" && c.status !== "Rejected" && c.target_closure_date && c.target_closure_date < today;
            return `
            <tr class="clickable" onclick="qmsCapaOpenDetail(${c.id})">
              <td>${c.capa_number}</td>
              <td>${c.title}</td>
              <td>${c.capa_source}</td>
              <td>${c.department || "—"}</td>
              <td>${qmsBadge(c.status)}</td>
              <td>${overdue ? `<span class="badge badge-overdue">${c.target_closure_date} (Overdue)</span>` : (c.target_closure_date || "—")}</td>
            </tr>`;
          }).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    container.innerHTML = `<div class="qms-empty"><p>Failed to load CAPAs: ${e.message}</p></div>`;
  }
}

// ── Create wizard ───────────────────────────────────────────────────────────

function qmsCapaOpenNew() {
  const meta = window.QMS_META || { capa_sources: [] };
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";
  overlay.id = "qms-capa-new-modal";
  overlay.innerHTML = `
    <div class="modal open qms-modal-lg">
      <div class="modal-header">
        <h2>New CAPA</h2>
        <button class="modal-close" onclick="document.getElementById('qms-capa-new-modal').remove()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="form-field span-2">
            <label>Title</label>
            <input type="text" id="qms-new-capa-title" placeholder="e.g. CAPA for cold storage excursion" />
          </div>
          <div class="form-field">
            <label>Source</label>
            <select id="qms-new-capa-source">${qmsOptions(meta.capa_sources, "Deviation")}</select>
          </div>
          <div class="form-field">
            <label>Source Reference</label>
            <input type="text" id="qms-new-capa-ref" placeholder="e.g. DEV-2026-0001" />
          </div>
          <div class="form-field">
            <label>Department</label>
            <input type="text" id="qms-new-capa-dept" />
          </div>
          <div class="form-field">
            <label>Target Closure Date</label>
            <input type="date" id="qms-new-capa-target" />
          </div>
          <div class="form-field span-2">
            <label>Problem Statement</label>
            <textarea id="qms-new-capa-problem"></textarea>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="document.getElementById('qms-capa-new-modal').remove()">Cancel</button>
        <button class="btn-primary" onclick="qmsCapaCreate()">Create CAPA</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}
window.qmsCapaOpenNew = qmsCapaOpenNew;

async function qmsCapaCreate() {
  const title = document.getElementById("qms-new-capa-title").value.trim();
  if (!title) { qmsToast("Title is required"); return; }
  const data = {
    title,
    capa_source: document.getElementById("qms-new-capa-source").value,
    source_reference: document.getElementById("qms-new-capa-ref").value.trim(),
    department: document.getElementById("qms-new-capa-dept").value.trim(),
    target_closure_date: document.getElementById("qms-new-capa-target").value,
    problem_statement: document.getElementById("qms-new-capa-problem").value.trim(),
  };
  try {
    const capa = await qmsPostJSON("/qms/capa", data);
    document.getElementById("qms-capa-new-modal").remove();
    qmsToast(`Created ${capa.capa_number}`);
    qmsCapaOpenDetail(capa.id);
  } catch (e) {
    qmsToast("Failed to create CAPA: " + e.message);
  }
}
window.qmsCapaCreate = qmsCapaCreate;

// ── Detail view ─────────────────────────────────────────────────────────────

async function qmsCapaOpenDetail(id) {
  qmsCapaCurrentId = id;
  qmsCapaActiveTab = "overview";
  const body = document.getElementById("qms-capa-body");
  body.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading CAPA…</div>`;
  try {
    const capa = await qmsFetch(`/qms/capa/${id}`);
    body.innerHTML = `
      <div class="qms-page-header">
        <div>
          <button class="btn-secondary" style="margin-bottom:10px;padding:5px 12px;font-size:12px" onclick="qmsCapaShowList()">&larr; All CAPAs</button>
          <div class="qms-detail-number">${capa.capa_number} · Source: ${capa.capa_source}</div>
          <div class="qms-detail-title">${capa.title}</div>
          <div class="qms-detail-meta" id="qms-capa-meta">${qmsCapaMetaHTML(capa)}</div>
        </div>
        <div class="qms-header-actions">
          <button class="btn-secondary" onclick="qmsCapaPrint(${id})">Print</button>
          <button class="btn-secondary" onclick="qmsCapaExportDocx(${id})">Export DOCX</button>
        </div>
      </div>
      <div class="qms-body">
        <div class="qms-tabs" id="qms-capa-tabs">
          ${["overview", "actions", "effectiveness", "deviations", "attachments", "comments", "audit", "approval"]
            .map(t => `<button class="qms-tab ${t === qmsCapaActiveTab ? "active" : ""}" onclick="qmsCapaSwitchTab('${t}')">${qmsCapaTabLabel(t)}</button>`).join("")}
        </div>
        <div id="qms-capa-tab-body"></div>
      </div>
    `;
    qmsCapaRenderTab(capa);
  } catch (e) {
    body.innerHTML = `<div class="qms-empty"><p>Failed to load CAPA: ${e.message}</p></div>`;
  }
}
window.qmsCapaOpenDetail = qmsCapaOpenDetail;

function qmsCapaMetaHTML(capa) {
  return `
    <span>${qmsBadge(capa.status)}</span>
    <span>Department: ${capa.department || "—"}</span>
    <span>Source Ref: ${capa.source_reference || "—"}</span>
    <span>Target Closure: ${capa.target_closure_date || "—"}</span>
  `;
}

function qmsCapaTabLabel(t) {
  return {
    overview: "Overview", actions: "Actions", effectiveness: "Effectiveness Check",
    deviations: "Linked Deviations", attachments: "Attachments", comments: "Comments",
    audit: "Audit Trail", approval: "Approval",
  }[t] || t;
}

async function qmsCapaSwitchTab(tab) {
  qmsCapaActiveTab = tab;
  const order = ["overview", "actions", "effectiveness", "deviations", "attachments", "comments", "audit", "approval"];
  document.querySelectorAll("#qms-capa-tabs .qms-tab").forEach((b, i) => b.classList.toggle("active", order[i] === tab));
  const capa = await qmsFetch(`/qms/capa/${qmsCapaCurrentId}`);
  qmsCapaRenderTab(capa);
}
window.qmsCapaSwitchTab = qmsCapaSwitchTab;

function qmsCapaRenderTab(capa) {
  const el = document.getElementById("qms-capa-tab-body");
  const id = capa.id;

  if (qmsCapaActiveTab === "overview") {
    el.innerHTML = `
      <div class="qms-section-card">
        <h3>AI CAPA Draft Assistant</h3>
        <p style="font-size:12.5px;color:var(--text-muted);margin-bottom:12px">
          Suggests a refined problem statement, root cause, and corrective/preventive actions.
        </p>
        <button class="btn-primary" onclick="qmsCapaSuggestDraft(${id})"><span class=\'icon\' data-lucide=\'sparkles\'></span> Suggest CAPA Draft with AI</button>
        <div id="qms-capa-draft-suggestion" style="margin-top:12px"></div>
      </div>
      <div class="qms-section-card">
        <h3>CAPA Details</h3>
        <div class="form-grid">
          <div class="form-field"><label>Target Closure Date</label><input type="date" id="qms-cov-target" value="${capa.target_closure_date || ""}" /></div>
          <div class="form-field"><label>QA Reviewer</label><input type="text" id="qms-cov-qa" value="${capa.qa_reviewer || ""}" /></div>
          <div class="form-field span-2"><label>Problem Statement</label><textarea id="qms-cov-problem">${capa.problem_statement || ""}</textarea></div>
          <div class="form-field span-2"><label>Root Cause</label><textarea id="qms-cov-rootcause">${capa.root_cause || ""}</textarea></div>
        </div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="qmsCapaSaveOverview(${id})">Save</button>
        </div>
      </div>
    `;
  } else if (qmsCapaActiveTab === "actions") {
    qmsCapaRenderActions(id);
  } else if (qmsCapaActiveTab === "effectiveness") {
    qmsCapaRenderEffectiveness(id);
  } else if (qmsCapaActiveTab === "deviations") {
    qmsCapaRenderLinkedDeviations(id);
  } else if (qmsCapaActiveTab === "attachments") {
    el.innerHTML = `<div id="qms-attachments-capa-${id}"></div>`;
    qmsRenderAttachments(`qms-attachments-capa-${id}`, "capa", id);
  } else if (qmsCapaActiveTab === "comments") {
    el.innerHTML = `<div id="qms-comments-capa-${id}"></div>`;
    qmsRenderComments(`qms-comments-capa-${id}`, "capa", id);
  } else if (qmsCapaActiveTab === "audit") {
    el.innerHTML = `<div id="qms-audit-capa-${id}"></div>`;
    qmsRenderAuditTrail(`qms-audit-capa-${id}`, "capa", id);
  } else if (qmsCapaActiveTab === "approval") {
    el.innerHTML = `<div id="qms-approval-capa-${id}"></div>`;
    qmsCapaRenderApprovalTab(id);
  }
}

async function qmsCapaSuggestDraft(id) {
  const el = document.getElementById("qms-capa-draft-suggestion");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Generating draft…</div>`;
  try {
    const s = await qmsPostJSON(`/qms/capa/${id}/suggest-draft`, {});
    el.innerHTML = `
      <div class="qms-panel-item" style="flex-direction:column;align-items:stretch">
        <div><strong>Problem Statement:</strong> ${s.problem_statement || ""}</div>
        <div><strong>Root Cause:</strong> ${s.root_cause || ""}</div>
        <div><strong>Corrective Actions:</strong> ${(s.corrective_actions || []).map(a => a.description).join("; ")}</div>
        <div><strong>Preventive Actions:</strong> ${(s.preventive_actions || []).map(a => a.description).join("; ")}</div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick='qmsCapaApplyDraft(${id}, ${JSON.stringify(s).replace(/'/g, "&apos;")})'>Apply to Record</button>
        </div>
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<p style="font-size:12.5px;color:var(--text-muted)">Failed: ${e.message}</p>`;
  }
}
window.qmsCapaSuggestDraft = qmsCapaSuggestDraft;

async function qmsCapaApplyDraft(id, s) {
  try {
    await qmsPutJSON(`/qms/capa/${id}`, { problem_statement: s.problem_statement || "", root_cause: s.root_cause || "" });
    for (const a of (s.corrective_actions || [])) {
      await qmsPostJSON(`/qms/capa/${id}/actions`, { action_type: "Corrective", description: a.description, owner: a.owner || "" });
    }
    for (const a of (s.preventive_actions || [])) {
      await qmsPostJSON(`/qms/capa/${id}/actions`, { action_type: "Preventive", description: a.description, owner: a.owner || "" });
    }
    qmsToast("Draft applied to CAPA record");
    qmsCapaOpenDetail(id);
  } catch (e) {
    qmsToast("Failed to apply draft: " + e.message);
  }
}
window.qmsCapaApplyDraft = qmsCapaApplyDraft;

async function qmsCapaSaveOverview(id) {
  const data = {
    target_closure_date: document.getElementById("qms-cov-target").value,
    qa_reviewer: document.getElementById("qms-cov-qa").value.trim(),
    problem_statement: document.getElementById("qms-cov-problem").value,
    root_cause: document.getElementById("qms-cov-rootcause").value,
  };
  try {
    await qmsPutJSON(`/qms/capa/${id}`, data);
    qmsToast("Saved");
  } catch (e) {
    qmsToast("Save failed: " + e.message);
  }
}
window.qmsCapaSaveOverview = qmsCapaSaveOverview;

// ── Actions tab ─────────────────────────────────────────────────────────────

async function qmsCapaRenderActions(id) {
  const el = document.getElementById("qms-capa-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading actions…</div>`;
  const actions = await qmsFetch(`/qms/capa/${id}/actions`);
  const meta = window.QMS_META || { capa_action_types: [], capa_action_statuses: [] };
  const today = new Date().toISOString().slice(0, 10);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Add Action</h3>
      <div class="form-grid">
        <div class="form-field"><label>Type</label><select id="qms-action-type">${qmsOptions(meta.capa_action_types, "Corrective")}</select></div>
        <div class="form-field"><label>Owner</label><input type="text" id="qms-action-owner" /></div>
        <div class="form-field"><label>Due Date</label><input type="date" id="qms-action-due" /></div>
        <div class="form-field span-2"><label>Description</label><textarea id="qms-action-desc"></textarea></div>
      </div>
      <div class="qms-form-actions">
        <button class="btn-primary" onclick="qmsCapaAddAction(${id})">Add</button>
      </div>
    </div>
    ${actions.length ? `
      <table class="qms-table">
        <thead><tr><th>Type</th><th>Description</th><th>Owner</th><th>Due Date</th><th>Status</th><th>Escalated</th><th></th></tr></thead>
        <tbody>${actions.map(a => {
          const overdue = a.status !== "Completed" && a.due_date && a.due_date < today;
          return `
          <tr>
            <td>${a.action_type}</td><td>${a.description}</td><td>${a.owner || "—"}</td>
            <td>${overdue ? `<span class="badge badge-overdue">${a.due_date}</span>` : (a.due_date || "—")}</td>
            <td>${qmsBadge(a.status)}</td>
            <td>${a.escalated ? `Yes — ${a.escalated_to || ""}` : "No"}</td>
            <td>
              ${a.status !== "Completed" ? `<a href="#" onclick="qmsCapaCompleteAction(${id},${a.id});return false;">Complete</a>` : ""}
              ${!a.escalated && a.status !== "Completed" ? ` · <a href="#" onclick="qmsCapaEscalateAction(${id},${a.id});return false;">Escalate</a>` : ""}
            </td>
          </tr>`;
        }).join("")}</tbody>
      </table>` : `<div class="qms-empty"><p>No actions recorded yet.</p></div>`}
  `;
}

async function qmsCapaAddAction(id) {
  const description = document.getElementById("qms-action-desc").value.trim();
  if (!description) { qmsToast("Description is required"); return; }
  const data = {
    action_type: document.getElementById("qms-action-type").value,
    description,
    owner: document.getElementById("qms-action-owner").value.trim(),
    due_date: document.getElementById("qms-action-due").value,
  };
  try {
    await qmsPostJSON(`/qms/capa/${id}/actions`, data);
    qmsCapaRenderActions(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCapaAddAction = qmsCapaAddAction;

async function qmsCapaCompleteAction(capaId, actionId) {
  const today = new Date().toISOString().slice(0, 10);
  try {
    await qmsPostJSON(`/qms/capa/${capaId}/actions`, { id: actionId, status: "Completed", completion_date: today });
    qmsCapaRenderActions(capaId);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCapaCompleteAction = qmsCapaCompleteAction;

async function qmsCapaEscalateAction(capaId, actionId) {
  const escalatedTo = prompt("Escalate to (name/role):");
  if (!escalatedTo) return;
  const today = new Date().toISOString().slice(0, 10);
  try {
    await qmsPostJSON(`/qms/capa/actions/${actionId}/escalate`, { escalated_to: escalatedTo, escalated_date: today });
    qmsToast("Action escalated");
    qmsCapaRenderActions(capaId);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCapaEscalateAction = qmsCapaEscalateAction;

// ── Effectiveness tab ─────────────────────────────────────────────────────────

async function qmsCapaRenderEffectiveness(id) {
  const el = document.getElementById("qms-capa-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading effectiveness checks…</div>`;
  const checks = await qmsFetch(`/qms/capa/${id}/effectiveness`);
  el.innerHTML = `
    <div class="qms-section-card">
      <h3>AI-Suggested Effectiveness Checks</h3>
      <button class="btn-secondary" onclick="qmsCapaSuggestEffectiveness(${id})"><span class=\'icon\' data-lucide=\'sparkles\'></span> Suggest Effectiveness Checks with AI</button>
      <div id="qms-capa-eff-suggestions" style="margin-top:12px"></div>
    </div>
    ${checks.length ? `
      <table class="qms-table">
        <thead><tr><th>Criterion</th><th>Method</th><th>Timeframe</th><th>Acceptable Result</th><th>Status</th></tr></thead>
        <tbody>${checks.map(c => `<tr><td>${c.check_criterion}</td><td>${c.method}</td><td>${c.timeframe}</td><td>${c.acceptable_result}</td><td>${qmsBadge(c.status)}</td></tr>`).join("")}</tbody>
      </table>` : `<div class="qms-empty"><p>No effectiveness checks recorded yet.</p></div>`}
  `;
}

async function qmsCapaSuggestEffectiveness(id) {
  const el = document.getElementById("qms-capa-eff-suggestions");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Generating suggestions…</div>`;
  try {
    const suggestions = await qmsPostJSON(`/qms/capa/${id}/suggest-effectiveness`, {});
    el.innerHTML = suggestions.length ? suggestions.map(s => `
      <div class="qms-panel-item">
        <div>
          <strong>${s.check_criterion}</strong>
          <div>Method: ${s.method} · Timeframe: ${s.timeframe}</div>
          <div class="qms-panel-item-meta">Acceptable Result: ${s.acceptable_result}</div>
        </div>
        <button class="btn-secondary" style="padding:5px 12px;font-size:11px" onclick='qmsCapaAcceptEffectiveness(${id}, ${JSON.stringify(s).replace(/'/g, "&apos;")})'>Add</button>
      </div>`).join("") : `<p style="font-size:12.5px;color:var(--text-muted)">No suggestions returned.</p>`;
  } catch (e) {
    el.innerHTML = `<p style="font-size:12.5px;color:var(--text-muted)">Failed: ${e.message}</p>`;
  }
}
window.qmsCapaSuggestEffectiveness = qmsCapaSuggestEffectiveness;

async function qmsCapaAcceptEffectiveness(id, suggestion) {
  try {
    await qmsPostJSON(`/qms/capa/${id}/effectiveness`, suggestion);
    qmsToast("Added");
    qmsCapaRenderEffectiveness(id);
  } catch (e) {
    qmsToast("Failed: " + e.message);
  }
}
window.qmsCapaAcceptEffectiveness = qmsCapaAcceptEffectiveness;

// ── Linked deviations tab ──────────────────────────────────────────────────────

async function qmsCapaRenderLinkedDeviations(id) {
  const el = document.getElementById("qms-capa-tab-body");
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading linked deviations…</div>`;
  const deviations = await qmsFetch(`/qms/capa/${id}/deviations`);
  el.innerHTML = deviations.length ? `
    <table class="qms-table">
      <thead><tr><th>Deviation Number</th><th>Title</th><th>Type</th><th>Status</th></tr></thead>
      <tbody>${deviations.map(d => `<tr class="clickable" onclick="document.getElementById('nav-qms-deviations') && document.getElementById('nav-qms-deviations').click()"><td>${d.deviation_number}</td><td>${d.title}</td><td>${qmsBadge(d.deviation_type)}</td><td>${qmsBadge(d.status)}</td></tr>`).join("")}</tbody>
    </table>` : `<div class="qms-empty"><p>No deviations linked to this CAPA.</p></div>`;
}

// ── Approval / status transition ──────────────────────────────────────────────

async function qmsCapaRenderApprovalTab(id) {
  const actions = [
    "Root Cause Analysis Started", "Corrective Actions Planned", "Preventive Actions Planned",
    "Implementation Started", "Effectiveness Check Started", "Submitted for QA Review",
    "Closed", "Rejected",
  ];
  qmsRenderApproval(`qms-approval-capa-${id}`, "capa", id, actions, `/qms/capa/${id}/approval`,
    () => qmsCapaRefreshApprovalTab(id));
}

async function qmsCapaRefreshApprovalTab(id) {
  const capa = await qmsFetch(`/qms/capa/${id}`);
  const metaEl = document.getElementById("qms-capa-meta");
  if (metaEl) metaEl.innerHTML = qmsCapaMetaHTML(capa);
  qmsCapaRenderApprovalTab(id);
}

// ── Print / Export ──────────────────────────────────────────────────────────

async function qmsCapaPrint(id) {
  try {
    const { markdown, title } = await qmsFetch(`/qms/capa/${id}/report`);
    const win = window.open("", "_blank");
    win.document.write(`<html><head><title>${title}</title></head><body>${window.marked ? marked.parse(markdown) : `<pre>${markdown}</pre>`}</body></html>`);
    win.document.close();
    win.print();
  } catch (e) {
    qmsToast("Failed to prepare print view: " + e.message);
  }
}
window.qmsCapaPrint = qmsCapaPrint;

async function qmsCapaExportDocx(id) {
  try {
    const res = await fetch(`/qms/capa/${id}/export/docx`, { method: "POST" });
    if (!res.ok) { qmsToast("Export failed"); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `CAPA_${id}.docx`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    qmsToast("Export error: " + e.message);
  }
}
window.qmsCapaExportDocx = qmsCapaExportDocx;
