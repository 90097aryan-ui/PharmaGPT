/*
 * workflow_panel.js — generic Workflow Engine review panel, shared by CAPA,
 * Change Control, and Document Control's "Workflow" tab (Deviations keep
 * their own richer, already-working Lifecycle tab in qms_deviations.js —
 * this is the same underlying pattern, generalized for the other three
 * modules so they don't each need a near-duplicate).
 *
 * Consumes one WorkflowContext-shaped object per record
 * (services/workflow_context.py): { record_type, record_id,
 * workflow_instance, current_step, current_user }. Every decision goes
 * through <routePrefix>/<id>/workflow/steps/<order>/decide — the engine is
 * never bypassed (services/workflow_engine.py::decide_step).
 *
 * Required actions (Problem 2): Approve, Reject, Request Changes, Delegate.
 * "Request Changes" is a labeled variant of the engine's `reject` decision
 * (comments tagged) — see docs/plan Assumptions. Comments are mandatory for
 * Reject and Request Changes. Delegate reassigns the step's named
 * approver(s) via the existing generic assign_approvers endpoint (no new
 * decision type).
 */

async function renderWorkflowPanel(containerId, recordType, routePrefix, recordId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="qms-loading"><div class="qms-spinner"></div> Loading workflow…</div>`;
  let wf;
  try {
    wf = await qmsFetch(`${routePrefix}/${recordId}/workflow`);
  } catch (e) {
    el.innerHTML = `<div class="qms-empty"><p>Failed to load workflow: ${e.message}</p></div>`;
    return;
  }

  if (!wf.instance) {
    el.innerHTML = `
      <div class="qms-section-card">
        <h3>Not Started</h3>
        <p style="font-size:12.5px;color:var(--text-muted);margin-bottom:12px">
          This record has not entered the Workflow Engine yet. Starting it creates the first gated step.
        </p>
        <button class="btn-primary" onclick="wfPanelStart('${containerId}','${recordType}','${routePrefix}',${recordId})">Start Workflow</button>
      </div>`;
    return;
  }

  const user = (window.PharmaAuth && window.PharmaAuth.getUser()) || {};
  const instance = wf.instance;
  const steps = wf.steps || [];

  el.innerHTML = `
    <div class="qms-section-card">
      <h3>Workflow Status</h3>
      <div class="qms-detail-meta">
        <span>${qmsBadge(instance.status === "in_progress" ? "In Progress" : instance.status === "completed" ? "Completed" : "Rejected")}</span>
        <span>Step ${instance.current_step_order} of ${steps.length}</span>
      </div>
    </div>
    <div class="qms-workflow-stepper">
      ${steps.map(s => wfPanelStepHTML(containerId, recordType, routePrefix, recordId, s, instance, user)).join("")}
    </div>
  `;
}
window.renderWorkflowPanel = renderWorkflowPanel;

function wfPanelStepHTML(containerId, recordType, routePrefix, recordId, step, instance, user) {
  const isCurrent = instance.status === "in_progress" && step.step_order === instance.current_step_order;
  const stateClass = step.status === "approved" ? "success" : step.status === "rejected" ? "critical"
    : isCurrent ? "info" : "";

  let body = "";
  if (step.status !== "pending") {
    body = `<div class="qms-panel-item-meta">${qmsBadge(step.status)} by ${step.decided_by || "—"} on ${step.decided_at || "—"}${step.comments ? ` — "${step.comments}"` : ""}</div>`;
  } else if (isCurrent) {
    body = wfPanelActionHTML(containerId, recordType, routePrefix, recordId, step, user);
  } else {
    body = `<div class="qms-panel-item-meta">Not yet reached</div>`;
  }

  return `
    <div class="qms-stat-card ${stateClass}" style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong>${step.step_order}. ${step.step_name}</strong>
        ${step.step_type === "approval" ? wfPanelApproversBadge(step.approvers) : ""}
      </div>
      ${body}
    </div>
  `;
}

function wfPanelApproversBadge(approvers) {
  if (!approvers || !approvers.length) return `<span class="qms-panel-item-meta">No approver assigned</span>`;
  return `<span class="qms-panel-item-meta">Assigned To: ${approvers.map(a => a.display_name || a.user_id).join(", ")}</span>`;
}

function wfPanelActionHTML(containerId, recordType, routePrefix, recordId, step, user) {
  const formId = `wf-panel-${recordType}-${recordId}-${step.step_order}`;

  if (step.step_type !== "approval") {
    if (!user.role || !(step.eligible_roles || "").split(",").includes(user.role)) {
      return `<div class="qms-panel-item-meta">Waiting for a user with an eligible role to advance this step.</div>`;
    }
    return `
      <div class="qms-form-actions" style="margin-top:8px">
        <button class="btn-primary" onclick="wfPanelDecide('${containerId}','${recordType}','${routePrefix}',${recordId},${step.step_order},'advance','${formId}')">Mark Complete</button>
      </div>
    `;
  }

  const approvers = step.approvers || [];
  if (!approvers.length) {
    return `
      <div class="form-grid" style="margin-top:8px">
        <div class="form-field"><label>Approver User ID</label><input type="text" id="${formId}-uid" placeholder="Supabase user id" /></div>
        <div class="form-field"><label>Display Name</label><input type="text" id="${formId}-name" placeholder="Full name" /></div>
      </div>
      <div class="qms-form-actions">
        <button class="btn-secondary" onclick="wfPanelAssign('${containerId}','${recordType}','${routePrefix}',${recordId},${step.step_order},'${formId}')">Assign Approver</button>
      </div>
      <p style="font-size:11.5px;color:var(--text-muted);margin-top:4px">Awaiting approver assignment — this step cannot be decided until at least one approver is assigned.</p>
    `;
  }

  const isApprover = approvers.some(a => a.user_id === user.user_id);
  if (!isApprover) {
    return `<div class="qms-panel-item-meta">Waiting for ${approvers.map(a => a.display_name || a.user_id).join(" or ")} to decide.</div>`;
  }

  return `
    <div class="form-field" style="margin-top:8px"><label>Comments</label><input type="text" id="${formId}-comments" placeholder="Required for Reject / Request Changes" /></div>
    <div class="qms-form-actions">
      <button class="btn-primary" onclick="wfPanelDecide('${containerId}','${recordType}','${routePrefix}',${recordId},${step.step_order},'approve','${formId}')">Approve</button>
      <button class="btn-secondary" onclick="wfPanelDecide('${containerId}','${recordType}','${routePrefix}',${recordId},${step.step_order},'reject','${formId}')">Reject</button>
      <button class="btn-secondary" onclick="wfPanelDecide('${containerId}','${recordType}','${routePrefix}',${recordId},${step.step_order},'request_changes','${formId}')">Request Changes</button>
      <button class="btn-secondary" onclick="wfPanelDelegate('${containerId}','${recordType}','${routePrefix}',${recordId},${step.step_order},'${formId}')">Delegate</button>
    </div>
  `;
}

async function wfPanelStart(containerId, recordType, routePrefix, recordId) {
  try {
    await qmsPostJSON(`${routePrefix}/${recordId}/workflow/start`, {});
    qmsToast("Workflow started");
    renderWorkflowPanel(containerId, recordType, routePrefix, recordId);
  } catch (e) {
    qmsToast("Failed to start workflow: " + e.message);
  }
}
window.wfPanelStart = wfPanelStart;

async function wfPanelAssign(containerId, recordType, routePrefix, recordId, stepOrder, formId) {
  const user_id = document.getElementById(`${formId}-uid`).value.trim();
  const display_name = document.getElementById(`${formId}-name`).value.trim();
  if (!user_id) { qmsToast("Approver User ID is required"); return; }
  try {
    await qmsPostJSON(`${routePrefix}/${recordId}/workflow/steps/${stepOrder}/assign`, {
      approvers: [{ user_id, display_name }],
    });
    qmsToast("Approver assigned");
    renderWorkflowPanel(containerId, recordType, routePrefix, recordId);
  } catch (e) {
    qmsToast("Failed to assign approver: " + e.message);
  }
}
window.wfPanelAssign = wfPanelAssign;

async function wfPanelDelegate(containerId, recordType, routePrefix, recordId, stepOrder, formId) {
  const user_id = prompt("Delegate to — Supabase user id:");
  if (!user_id) return;
  const display_name = prompt("Delegate to — display name (optional):") || "";
  try {
    await qmsPostJSON(`${routePrefix}/${recordId}/workflow/steps/${stepOrder}/assign`, {
      approvers: [{ user_id, display_name }],
    });
    qmsToast("Delegated");
    renderWorkflowPanel(containerId, recordType, routePrefix, recordId);
  } catch (e) {
    qmsToast("Failed to delegate: " + e.message);
  }
}
window.wfPanelDelegate = wfPanelDelegate;

async function wfPanelDecide(containerId, recordType, routePrefix, recordId, stepOrder, uiAction, formId) {
  const commentsEl = document.getElementById(`${formId}-comments`);
  let comments = commentsEl ? commentsEl.value.trim() : "";

  if ((uiAction === "reject" || uiAction === "request_changes") && !comments) {
    qmsToast("Comments are required for " + (uiAction === "reject" ? "Reject" : "Request Changes"));
    return;
  }
  let decision = uiAction;
  if (uiAction === "request_changes") {
    decision = "reject";
    comments = `[Request Changes] ${comments}`;
  }

  if (!window.PharmaESign) { qmsToast("Electronic Signature dialog failed to load"); return; }

  // 21 CFR Part 11 / EU GMP Annex 11: this GMP decision requires a fresh
  // Electronic Signature (password re-confirmation + meaning + reason) —
  // see pharmagpt/services/esignature_service.py.
  const meaningByDecision = { approve: "Approved", reject: "Rejected", advance: "Reviewed" };
  window.PharmaESign.open({
    meaning: meaningByDecision[decision] || "Approved",
    onConfirm: async ({ password, meaning, reason }) => {
      await qmsPostJSON(`${routePrefix}/${recordId}/workflow/steps/${stepOrder}/decide`, {
        decision, comments, password, meaning, reason,
      });
      qmsToast("Recorded");
      renderWorkflowPanel(containerId, recordType, routePrefix, recordId);
    },
  });
}
window.wfPanelDecide = wfPanelDecide;
