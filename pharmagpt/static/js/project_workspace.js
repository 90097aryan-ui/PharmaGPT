// project_workspace.js — PharmaGPT v1.0 Module 3: "One Project = One Workspace".
// Opens a unified Project Workspace (Enterprise Workspace shell) when a project
// is selected, replacing the standalone Equipment/Documents/Insights nav items
// and the retired legacy Validation Workspace. Depends on window.activeProject
// (set by projects.js) and reuses equipment.js/documents.js/insights.js's
// existing rendering logic unchanged (their target element IDs were simply
// moved into this workspace's Equipment/Documents tab panels).
// All top-level functions are `pw`-prefixed per the DEC-020 collision lesson.

const PW_TABS = [
  { id: "overview",      label: "Overview" },
  { id: "equipment",     label: "Equipment" },
  { id: "documents",     label: "Documents" },
  { id: "risk",          label: "Risk Assessment" },
  { id: "urs",           label: "URS" },
  { id: "qualification", label: "Qualification" },
  { id: "report",        label: "Validation Report" },
  { id: "tasks",         label: "Tasks" },
  { id: "approvals",     label: "Approvals" },
  { id: "history",       label: "History" },
];

let pwActiveTab = "overview";

function pwOpenWorkspace(project) {
  if (!project) return;
  pwActiveTab = "overview";

  document.querySelectorAll(".sidebar-item[data-view]").forEach(n => n.classList.remove("active"));
  document.querySelectorAll("main[id^='view-']").forEach(v => v.style.display = "none");
  document.getElementById("view-project-workspace").style.display = "flex";
  if (window.__ws_setActiveView) window.__ws_setActiveView("view-project-workspace");

  document.getElementById("pw-title").textContent = project.name;
  document.getElementById("pw-sub").textContent =
    [project.validation_type, project.equipment_name, project.department].filter(Boolean).join("  ·  ") || "No additional details";

  const tagsEl = document.getElementById("pw-tags");
  tagsEl.innerHTML = `
    <span class="ent-ws-tag ${project.status ? "" : "is-empty"}">${project.status ? pwEsc(project.status) : "No status"}</span>
    <span class="ent-ws-tag ${project.risk_category ? "" : "is-empty"}">${project.risk_category ? pwEsc(project.risk_category) : "Risk category not set"}</span>
  `;

  if (window.Workspace) {
    window.Workspace.renderBreadcrumb("pw-breadcrumb", [
      { label: "Dashboard" }, { label: project.name, current: true },
    ]);
  }

  document.getElementById("pw-tabs").innerHTML = PW_TABS.map(t =>
    `<button class="ws-tab ${t.id === pwActiveTab ? "active" : ""}" onclick="pwSwitchTab('${t.id}')">${t.label}</button>`
  ).join("");

  pwRenderTab();
  if (window.refreshIcons) window.refreshIcons();
}
window.pwOpenWorkspace = pwOpenWorkspace;

function pwBackToDashboard() {
  document.querySelectorAll("main[id^='view-']").forEach(v => v.style.display = "none");
  document.getElementById("view-dashboard").style.display = "flex";
  if (window.__ws_setActiveView) window.__ws_setActiveView("view-dashboard");

  const nav = document.getElementById("nav-dashboard");
  if (nav) { document.querySelectorAll(".sidebar-item[data-view]").forEach(n => n.classList.remove("active")); nav.classList.add("active"); }
  if (window.loadDashboard) window.loadDashboard();
}
window.pwBackToDashboard = pwBackToDashboard;

function pwSwitchTab(tab) {
  pwActiveTab = tab;
  document.querySelectorAll("#pw-tabs .ws-tab").forEach(b => b.classList.remove("active"));
  const idx = PW_TABS.findIndex(t => t.id === tab);
  const btns = document.querySelectorAll("#pw-tabs .ws-tab");
  if (btns[idx]) btns[idx].classList.add("active");
  pwRenderTab();
}
window.pwSwitchTab = pwSwitchTab;

/** Return to the Project Workspace's Equipment tab (used by equipment.js's
 * eqBackToList() after retiring the standalone Equipment list view). */
function pwShowTab(tab) {
  document.querySelectorAll("main[id^='view-']").forEach(v => v.style.display = "none");
  document.getElementById("view-project-workspace").style.display = "flex";
  if (window.__ws_setActiveView) window.__ws_setActiveView("view-project-workspace");
  pwSwitchTab(tab);
}
window.pwShowTab = pwShowTab;

function pwRenderTab() {
  document.querySelectorAll(".pw-tab-panel").forEach(p => {
    p.classList.toggle("active", p.dataset.pwTab === pwActiveTab);
  });

  const project = window.activeProject;
  if (!project) return;

  if (pwActiveTab === "overview") {
    pwRenderOverview(project);
  } else if (pwActiveTab === "equipment") {
    if (window.loadEquipment) window.loadEquipment();
  } else if (pwActiveTab === "documents") {
    const subtitle = document.getElementById("doc-project-subtitle");
    if (subtitle) subtitle.textContent = `Project: ${project.name}`;
    if (window.loadDocuments) window.loadDocuments();
    if (window.loadInsights) window.loadInsights();
  } else if (pwActiveTab === "history") {
    pwRenderHistory(project.id);
  }

  if (window.refreshIcons) window.refreshIcons();
}

function pwField(label, value) {
  const display = (value === null || value === undefined || value === "") ? "" : value;
  return `<div class="eq-detail-field"><label>${label}</label><span${display ? "" : ' class="eq-empty-value"'}>${display ? pwEsc(String(display)) : "Not set"}</span></div>`;
}

function pwRenderOverview(project) {
  const grid = document.getElementById("pw-overview-grid");
  if (!grid) return;
  grid.innerHTML = [
    pwField("Project Name", project.name),
    pwField("Validation Type", project.validation_type),
    pwField("Status", project.status),
    pwField("Risk Category", project.risk_category),
    pwField("Protocol Number", project.protocol_number),
    pwField("Report Number", project.report_number),
    pwField("Owner", project.owner),
    pwField("Approver", project.approver),
    pwField("Target Date", project.target_date),
    pwField("Equipment Name (legacy)", project.equipment_name),
    pwField("Manufacturer", project.manufacturer),
    pwField("Department", project.department),
    pwField("Created", project.created_at ? new Date(project.created_at).toLocaleString() : ""),
  ].join("");
}

async function pwRenderHistory(projectId) {
  const el = document.getElementById("pw-history-list");
  if (!el) return;
  el.innerHTML = "Loading…";
  try {
    const res = await fetch(`/qms/project/${projectId}/audit-trail`);
    const entries = await res.json();

    if (!entries.length) {
      el.innerHTML = `<div class="eq-empty" style="padding:32px 0">
        <span class='icon' data-lucide='history' style="width:28px;height:28px;opacity:0.5"></span>
        <p>No history recorded yet.</p>
      </div>`;
      if (window.refreshIcons) window.refreshIcons();
      return;
    }

    el.innerHTML = entries.slice().reverse().map(e => `
      <div class="qms-panel-item">
        <div>
          <div class="qms-audit-action">${pwEsc(e.action)}</div>
          ${e.detail ? `<div class="qms-panel-item-meta">${pwEsc(e.detail)}</div>` : ""}
        </div>
        <div class="qms-panel-item-meta">${new Date(e.created_at).toLocaleString()}</div>
      </div>
    `).join("");
  } catch {
    el.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Could not load project history.</p>';
  }
}

function pwEsc(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

document.addEventListener("DOMContentLoaded", () => {
  const backBtn = document.getElementById("pw-back-btn");
  if (backBtn) backBtn.addEventListener("click", pwBackToDashboard);
});
