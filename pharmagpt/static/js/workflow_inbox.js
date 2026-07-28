/*
 * workflow_inbox.js — Universal Workflow Inbox frontend. Renders
 * GET /workflow/inbox into the existing "Approval Queue" -> "Workflow
 * Inbox" nav destination (view-risk-approval / #workflow-inbox-body — see
 * templates/index.html). Deliberately generic: every row already carries
 * its own module/icon/route from the backend registry
 * (services/workflow_registry.py) — a future module needs zero changes
 * here, only a registry entry + template on the backend.
 */

// Client-side routing table: how to open a record once its module is
// known. Kept small and separate from the backend registry (which owns
// route_prefix/number_field/title_field) since this only needs "which view
// + which JS function opens this module's detail page" — one line per
// module, matching the same additive pattern as workflow_registry.py.
const WF_INBOX_OPEN_DETAIL = {
  deviation:       { view: "view-qms-deviations",     open: id => window.qmsDevOpenDetail(id),  tab: () => window.qmsDevSwitchTab("lifecycle") },
  capa:            { view: "view-qms-capa",           open: id => window.qmsCapaOpenDetail(id), tab: () => window.qmsCapaSwitchTab("workflow") },
  change_control:  { view: "view-qms-change-control", open: id => window.qmsCCOpenDetail(id),   tab: () => window.qmsCCSwitchTab("workflow") },
  document:        { view: "view-qms-documents",      open: id => window.qmsDocOpenDetail(id),  tab: () => window.qmsDocSwitchTab("workflow") },
};

const WF_INBOX_MODULE_LABELS = {
  deviation: "Deviation", capa: "CAPA", change_control: "Change Control", document: "SOP / Document",
};

let _wfInboxItems = [];

async function loadWorkflowInbox() {
  const el = document.getElementById("workflow-inbox-body");
  if (!el) return;
  el.innerHTML = `<div class="risk-ai-generating"><div class="spinner"></div></div>`;
  try {
    _wfInboxItems = await qmsFetch("/workflow/inbox");
  } catch (e) {
    el.innerHTML = `<div class="risk-empty"><p>Failed to load Workflow Inbox: ${e.message}</p></div>`;
    return;
  }
  wfInboxPopulateFilters(_wfInboxItems);
  wfInboxRender(_wfInboxItems);
  if (window.PharmaNotifications) window.PharmaNotifications.refresh();
}
window.loadWorkflowInbox = loadWorkflowInbox;

function wfInboxPopulateFilters(items) {
  const moduleSel = document.getElementById("wf-inbox-filter-module");
  const statusSel = document.getElementById("wf-inbox-filter-status");
  if (moduleSel && moduleSel.options.length <= 1) {
    const modules = [...new Set(items.map(i => i.module))];
    modules.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = WF_INBOX_MODULE_LABELS[m] || m;
      moduleSel.appendChild(opt);
    });
  }
  if (statusSel && statusSel.options.length <= 1) {
    ["In Progress", "Overdue"].forEach(s => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      statusSel.appendChild(opt);
    });
  }
  if (moduleSel && !moduleSel._wfBound) {
    moduleSel.addEventListener("change", wfInboxApplyFilters);
    moduleSel._wfBound = true;
  }
  if (statusSel && !statusSel._wfBound) {
    statusSel.addEventListener("change", wfInboxApplyFilters);
    statusSel._wfBound = true;
  }
  const search = document.getElementById("wf-inbox-search");
  if (search && !search._wfBound) {
    search.addEventListener("input", wfInboxApplyFilters);
    search._wfBound = true;
  }
}

function wfInboxApplyFilters() {
  const q = (document.getElementById("wf-inbox-search").value || "").toLowerCase().trim();
  const module = document.getElementById("wf-inbox-filter-module").value;
  const status = document.getElementById("wf-inbox-filter-status").value;

  let filtered = _wfInboxItems;
  if (module) filtered = filtered.filter(i => i.module === module);
  if (status === "Overdue") filtered = filtered.filter(i => i.overdue);
  else if (status) filtered = filtered.filter(i => i.status === status);
  if (q) {
    filtered = filtered.filter(i =>
      (i.title || "").toLowerCase().includes(q) || (i.record_number || "").toLowerCase().includes(q)
    );
  }
  wfInboxRender(filtered);
}
window.wfInboxApplyFilters = wfInboxApplyFilters;

function wfInboxStatusBadgeClass(item) {
  if (item.overdue) return "critical";
  return item.step_type === "approval" ? "info" : "";
}

function wfInboxRender(items) {
  const el = document.getElementById("workflow-inbox-body");
  if (!el) return;
  if (!items.length) {
    el.innerHTML = `
      <div class="risk-empty">
        <div class="risk-empty-icon"><span class='icon' data-lucide='inbox'></span></div>
        <h3>Nothing pending</h3>
        <p>All caught up — no Workflow Engine steps are waiting on you right now.</p>
      </div>`;
    if (window.lucide) window.lucide.createIcons();
    return;
  }

  el.innerHTML = `
    <table class="qms-table">
      <thead>
        <tr>
          <th>Module</th><th>Record Number</th><th>Title</th><th>Current Step</th>
          <th>Assigned To</th><th>Status</th><th>Due Date</th><th>Priority</th>
          <th>Submitted By</th><th>Submitted Date</th><th></th>
        </tr>
      </thead>
      <tbody>
        ${items.map(i => `
          <tr>
            <td><span class='icon' data-lucide='${i.module_icon}'></span> ${WF_INBOX_MODULE_LABELS[i.module] || i.module}</td>
            <td>${i.record_number || "—"}</td>
            <td>${i.title || "Untitled"}</td>
            <td>${i.current_step_name}</td>
            <td>${(i.assigned_to || []).join(", ") || "—"}</td>
            <td><span class="badge badge-${wfInboxStatusBadgeClass(i)}">${i.overdue ? "Overdue" : "In Progress"}</span></td>
            <td>${i.due_date || "—"}</td>
            <td>${i.priority}</td>
            <td>${i.submitted_by || "—"}</td>
            <td>${i.submitted_date ? new Date(i.submitted_date).toLocaleDateString() : "—"}</td>
            <td><button class="btn-secondary" onclick="wfInboxReview('${i.module}',${i.record_id})">Review</button></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  if (window.lucide) window.lucide.createIcons();
}

async function wfInboxReview(module, recordId) {
  const target = WF_INBOX_OPEN_DETAIL[module];
  if (!target) { qmsToast(`Unknown module '${module}'`); return; }
  if (window.showView) window.showView(target.view);
  await target.open(recordId);
  await target.tab();
}
window.wfInboxReview = wfInboxReview;

// Notification bell (Problem 4): the header bell (static/js/notifications.js)
// already polls /workflow/inbox itself as an "Awaiting My Decision" group —
// nothing further needed here.
