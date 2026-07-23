// equipment.js — PharmaGPT v1.0 Module 2: Equipment as a first-class entity.
// Manages the project-scoped Equipment list view and the Equipment Profile
// (Enterprise Workspace) detail page. Depends on window.activeProject (set by
// projects.js). All top-level functions are prefixed `eq` to avoid the
// cross-suite global-scope name collisions this codebase is known to have
// (see PROJECT_MEMORY/DECISIONS.md DEC-020) — these files are plain scripts
// sharing one global scope, not IIFE modules.

// ── State ─────────────────────────────────────────────────────────────────────
let eqCurrentEquipmentId = null;   // equipment being edited in the modal (null = create)
let eqActiveProfileId    = null;   // equipment currently shown in the Profile view
let eqActiveTab          = "overview";
let eqDocTypeCatalog     = [];

const EQ_TABS = ["overview", "specifications", "documentation", "qualification",
                 "validation-history", "related-documents", "related-risk", "future"];
const EQ_TAB_LABELS = {
  "overview": "Overview", "specifications": "Specifications", "documentation": "Documentation",
  "qualification": "Qualification", "validation-history": "Validation History",
  "related-documents": "Related Documents", "related-risk": "Related Risk Assessments",
  "future": "Future Modules",
};
const EQ_DOC_ROLE_LABELS = {
  user_manual: "User Manual", vendor_manual: "Vendor Manual", sop: "SOP", drawing: "Drawing",
  pnid: "P&ID", electrical_drawing: "Electrical Drawing", pneumatic_drawing: "Pneumatic Drawing",
  fat: "FAT", sat: "SAT", urs: "URS", other: "Other",
};
const EQ_FUTURE_MODULES = [
  { name: "Calibration", icon: "gauge" }, { name: "Preventive Maintenance", icon: "wrench" },
  { name: "Breakdown History", icon: "alert-triangle" }, { name: "Spare Parts", icon: "package" },
  { name: "Vendor Qualification", icon: "badge-check" }, { name: "Environmental Monitoring", icon: "thermometer" },
  { name: "Utilities", icon: "plug-zap" }, { name: "Asset Management", icon: "boxes" },
];

// ── List view ─────────────────────────────────────────────────────────────────

async function eqLoadList() {
  const subtitle = document.getElementById("eq-project-subtitle");
  if (!window.activeProject) {
    subtitle.textContent = "Select a project to manage its equipment.";
    document.getElementById("eq-list").innerHTML = "";
    document.getElementById("eq-empty").style.display = "flex";
    document.getElementById("eq-import-banner").style.display = "none";
    return;
  }
  subtitle.textContent = `Project: ${window.activeProject.name}`;

  try {
    const res = await fetch(`/projects/${window.activeProject.id}/equipment`);
    const equipment = await res.json();
    eqRenderList(equipment);
    eqRenderImportBanner(equipment);
  } catch {
    document.getElementById("eq-list").innerHTML =
      '<p style="color:var(--text-muted);font-size:13px">Could not load equipment.</p>';
  }
}

function eqRenderImportBanner(equipmentList) {
  const banner = document.getElementById("eq-import-banner");
  const proj = window.activeProject;
  const hasLegacyInfo = proj && (proj.equipment_name || "").trim().length > 0;
  if (equipmentList.length > 0 || !hasLegacyInfo) {
    banner.style.display = "none";
    return;
  }
  banner.style.display = "flex";
  banner.innerHTML = `
    <span><span class='icon' data-lucide='info' style="width:14px;height:14px;vertical-align:-2px;margin-right:6px"></span>
      This project has legacy equipment info ("${eqEsc(proj.equipment_name)}") not yet in a proper Equipment record.</span>
    <button class="btn-secondary" id="eq-import-btn">Import from Project Info</button>
  `;
  document.getElementById("eq-import-btn").addEventListener("click", eqImportLegacy);
  if (window.refreshIcons) window.refreshIcons();
}

async function eqImportLegacy() {
  if (!window.activeProject) return;
  try {
    const res = await fetch(`/projects/${window.activeProject.id}/equipment/import-legacy`, { method: "POST" });
    if (!res.ok) throw new Error();
    await eqLoadList();
  } catch {
    alert("Could not import legacy equipment info. Please try again.");
  }
}

function eqRenderList(equipmentList, opts) {
  // opts lets the Equipment Library (Phase 2 — company-wide, top-level view)
  // reuse this exact renderer instead of duplicating it: different target
  // container ids, and rows opened from here return to the Library instead
  // of the Project Workspace's equipment tab (see eqBackToList()). Every
  // existing call site (the Project Workspace's equipment tab) passes no
  // opts and keeps its original ids/behaviour unchanged.
  const { listId = "eq-list", emptyId = "eq-empty", countId = "eq-count",
          origin = "project-workspace", showProjectColumn = false } = opts || {};
  const listEl  = document.getElementById(listId);
  const emptyEl = document.getElementById(emptyId);
  const countEl = document.getElementById(countId);
  listEl.innerHTML = "";
  countEl.textContent = equipmentList.length ? `${equipmentList.length} record${equipmentList.length === 1 ? "" : "s"}` : "";

  if (!equipmentList.length) {
    emptyEl.style.display = "flex";
    return;
  }
  emptyEl.style.display = "none";

  equipmentList.forEach(eq => {
    const row = document.createElement("div");
    row.className = "eq-row";
    row.innerHTML = `
      <div class="eq-icon"><span class='icon' data-lucide='cog'></span></div>
      <div class="eq-info">
        <div class="eq-name">${eqEsc(eq.name)}</div>
        <div class="eq-meta">
          ${showProjectColumn && eq.project_name ? `<span>${eqEsc(eq.project_name)}</span>` : ""}
          ${eq.equipment_code ? `<span>${eqEsc(eq.equipment_code)}</span>` : ""}
          ${eq.equipment_type ? `<span>${eqEsc(eq.equipment_type)}</span>` : ""}
          ${eq.manufacturer ? `<span>${eqEsc(eq.manufacturer)}</span>` : ""}
          ${eq.department ? `<span>${eqEsc(eq.department)}</span>` : ""}
        </div>
      </div>
      <div class="eq-row-badges">
        ${eq.criticality ? `<span class="badge ${eqCriticalityBadgeClass(eq.criticality)}">${eqEsc(eq.criticality)}</span>` : ""}
        ${eq.qualification_status ? `<span class="badge ${eqStatusBadgeClass(eq.qualification_status)}">${eqEsc(eq.qualification_status)}</span>` : ""}
      </div>
      <div class="eq-row-actions">
        <button class="eq-btn-profile" data-id="${eq.id}"><span class='icon' data-lucide='layout-panel-left'></span> Profile</button>
        <button class="eq-btn-edit" data-id="${eq.id}"><span class='icon' data-lucide='pencil'></span> Edit</button>
        <button class="eq-btn-danger eq-btn-delete" data-id="${eq.id}" data-name="${eqEsc(eq.name)}"><span class='icon' data-lucide='trash-2'></span></button>
      </div>
    `;
    row.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      eqOpenProfile(eq.id, origin);
    });
    row.querySelector(".eq-btn-profile").addEventListener("click", (e) => { e.stopPropagation(); eqOpenProfile(eq.id, origin); });
    row.querySelector(".eq-btn-edit").addEventListener("click", (e) => { e.stopPropagation(); eqOpenModal(eq.id); });
    row.querySelector(".eq-btn-delete").addEventListener("click", (e) => {
      e.stopPropagation();
      eqConfirmDelete(e.currentTarget.dataset.id, e.currentTarget.dataset.name);
    });
    listEl.appendChild(row);
  });

  if (window.refreshIcons) window.refreshIcons();
}

// ── Equipment Library (Phase 2 — first-class, top-level, company-wide) ────────

async function eqLoadCompanyList() {
  const countEl = document.getElementById("eqlib-count");
  try {
    const res = await fetch("/equipment");
    const equipment = await res.json();
    eqRenderList(equipment, {
      listId: "eqlib-list", emptyId: "eqlib-empty", countId: "eqlib-count",
      origin: "library", showProjectColumn: true,
    });
  } catch {
    if (countEl) countEl.textContent = "";
    document.getElementById("eqlib-list").innerHTML =
      '<p style="color:var(--text-muted);font-size:13px">Could not load the Equipment Library.</p>';
  }
}
window.eqLoadCompanyList = eqLoadCompanyList;

function eqCriticalityBadgeClass(criticality) {
  const map = { "Critical": "badge-critical", "Major": "badge-medium", "Minor": "badge-low" };
  return map[criticality] || "badge-draft";
}

function eqStatusBadgeClass(status) {
  const map = {
    "Qualified": "badge-approved", "Validated": "badge-approved",
    "In Progress": "badge-in-progress",
    "Requalification Due": "badge-critical",
    "Not Started": "badge-draft",
  };
  return map[status] || "badge-draft";
}

// ── Add / Edit modal ──────────────────────────────────────────────────────────

async function eqOpenModal(equipmentId) {
  eqCurrentEquipmentId = equipmentId || null;
  const form = document.getElementById("eq-form");
  form.reset();

  document.getElementById("eq-modal-title").textContent = equipmentId ? "Edit Equipment" : "Add Equipment";
  document.getElementById("eq-modal-save").textContent = equipmentId ? "Save Changes" : "Add Equipment";

  if (equipmentId) {
    try {
      const res = await fetch(`/equipment/${equipmentId}`);
      const eq = await res.json();
      Object.keys(eq).forEach(key => {
        const input = document.getElementById(`eq-f-${key}`);
        if (input) input.value = eq[key] ?? "";
      });
    } catch {
      alert("Could not load equipment details.");
      return;
    }
  }

  await eqEnsureTypeCatalog();

  document.getElementById("eq-modal").classList.add("open");
  document.getElementById("eq-modal-overlay").classList.add("open");
}

function eqCloseModal() {
  document.getElementById("eq-modal").classList.remove("open");
  document.getElementById("eq-modal-overlay").classList.remove("open");
}

async function eqEnsureTypeCatalog() {
  if (eqDocTypeCatalog.length) return;
  try {
    const res = await fetch("/equipment/types");
    eqDocTypeCatalog = await res.json();
    const datalist = document.getElementById("eq-type-catalog");
    if (datalist) datalist.innerHTML = eqDocTypeCatalog.map(t => `<option value="${eqEsc(t)}"></option>`).join("");
  } catch { /* autocomplete is a nicety, fail silently */ }
}

const EQ_FIELD_IDS = [
  "equipment_code", "name", "category", "equipment_type", "tag_number", "model",
  "manufacturer", "vendor", "serial_number", "asset_number",
  "plant", "block", "department", "area", "room", "line",
  "installation_date", "commissioning_date",
  "qualification_status", "validation_status", "qualification_type", "criticality", "gmp_impact", "notes",
];

async function eqSubmitForm(e) {
  e.preventDefault();
  if (!window.activeProject) return;

  const payload = {};
  EQ_FIELD_IDS.forEach(key => {
    const input = document.getElementById(`eq-f-${key}`);
    if (input) payload[key] = input.value;
  });
  if (!payload.name.trim()) return;

  const saveBtn = document.getElementById("eq-modal-save");
  saveBtn.disabled = true;
  saveBtn.textContent = "Saving…";

  try {
    const url = eqCurrentEquipmentId ? `/equipment/${eqCurrentEquipmentId}` : `/projects/${window.activeProject.id}/equipment`;
    const method = eqCurrentEquipmentId ? "PUT" : "POST";
    const res = await fetch(url, {
      method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error();

    eqCloseModal();
    await eqLoadList();
    if (eqActiveProfileId && eqActiveProfileId === eqCurrentEquipmentId) await eqRenderProfile();
  } catch {
    alert("Could not save equipment. Please try again.");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = eqCurrentEquipmentId ? "Save Changes" : "Add Equipment";
  }
}

async function eqConfirmDelete(equipmentId, name) {
  if (!confirm(`Delete equipment "${name}"? This cannot be undone.`)) return;
  try {
    const res = await fetch(`/equipment/${equipmentId}`, { method: "DELETE" });
    if (!res.ok) throw new Error();
    await eqLoadList();
  } catch {
    alert("Could not delete equipment. Please try again.");
  }
}

// ── Equipment Profile (Enterprise Workspace) ──────────────────────────────────

let eqProfileOrigin = "project-workspace";   // "project-workspace" | "library" — where Back returns to

function eqOpenProfile(equipmentId, origin) {
  eqActiveProfileId = equipmentId;
  eqActiveTab = "overview";
  eqProfileOrigin = origin || "project-workspace";

  document.querySelectorAll(".sidebar-item[data-view]").forEach(n => n.classList.remove("active"));
  document.querySelectorAll("main[id^='view-']").forEach(v => v.style.display = "none");
  document.getElementById("view-equipment-profile").style.display = "flex";
  if (window.__ws_setActiveView) window.__ws_setActiveView("view-equipment-profile");

  eqRenderProfile();
}

function eqBackToList() {
  eqActiveProfileId = null;

  // Phase 2 — Equipment Library (company-wide, top-level): return to the
  // Library, not into whichever project happens to be active.
  if (eqProfileOrigin === "library") {
    if (window.eqShowLibraryView) window.eqShowLibraryView();
    return;
  }

  // PharmaGPT v1.0 Module 3 — the standalone Equipment list view was retired;
  // Equipment is now the "equipment" tab inside the unified Project Workspace
  // (see project_workspace.js::pwShowTab()).
  if (window.pwShowTab) {
    window.pwShowTab("equipment");
  } else {
    eqLoadList();
  }
}
window.eqBackToList = eqBackToList;

async function eqRenderProfile() {
  if (!eqActiveProfileId) return;
  let equipment;
  try {
    const res = await fetch(`/equipment/${eqActiveProfileId}`);
    if (!res.ok) throw new Error();
    equipment = await res.json();
  } catch {
    document.getElementById("eq-profile-body").innerHTML =
      '<p style="color:var(--text-muted);font-size:13px">Could not load this equipment record.</p>';
    return;
  }

  document.getElementById("eq-profile-title").textContent = equipment.name || "Equipment";
  document.getElementById("eq-profile-sub").textContent =
    [equipment.equipment_type, equipment.manufacturer, equipment.department].filter(Boolean).join("  ·  ") || "No additional details";

  const tagsEl = document.getElementById("eq-profile-tags");
  tagsEl.innerHTML = `
    <span class="ent-ws-tag ${equipment.equipment_code ? "" : "is-empty"}">${equipment.equipment_code ? eqEsc(equipment.equipment_code) : "No Equipment ID"}</span>
    <span class="ent-ws-tag ${equipment.criticality ? "" : "is-empty"}">${equipment.criticality ? eqEsc(equipment.criticality) : "Criticality not set"}</span>
  `;

  if (window.Workspace) {
    const parentCrumb = eqProfileOrigin === "library"
      ? { label: "Equipment Library" }
      : { label: window.activeProject ? window.activeProject.name : "Project" };
    window.Workspace.renderBreadcrumb("eq-profile-breadcrumb", [
      { label: "Dashboard" }, parentCrumb,
      { label: "Equipment" }, { label: equipment.name || "Profile", current: true },
    ]);
  }

  document.getElementById("eq-tabs").innerHTML = EQ_TABS.map(t =>
    `<button class="eq-tab ${t === eqActiveTab ? "active" : ""}" onclick="eqSwitchTab('${t}')">${EQ_TAB_LABELS[t]}</button>`
  ).join("");

  await eqRenderTab(equipment);
  if (window.refreshIcons) window.refreshIcons();
}

function eqSwitchTab(tab) {
  eqActiveTab = tab;
  document.querySelectorAll("#eq-tabs .eq-tab").forEach(b => b.classList.remove("active"));
  const idx = EQ_TABS.indexOf(tab);
  const btns = document.querySelectorAll("#eq-tabs .eq-tab");
  if (btns[idx]) btns[idx].classList.add("active");
  eqRenderProfile();
}
window.eqSwitchTab = eqSwitchTab;

function eqField(label, value, empty) {
  const display = (value === null || value === undefined || value === "") ? "" : value;
  return `<div class="eq-detail-field"><label>${label}</label><span${display ? "" : ' class="eq-empty-value"'}>${display ? eqEsc(String(display)) : (empty || "Not set")}</span></div>`;
}

async function eqRenderTab(equipment) {
  const el = document.getElementById("eq-profile-body");

  if (eqActiveTab === "overview") {
    el.innerHTML = `
      <div class="eq-detail-grid">
        ${eqField("Equipment ID", equipment.equipment_code)}
        ${eqField("Category", equipment.category)}
        ${eqField("Equipment Type", equipment.equipment_type)}
        ${eqField("Manufacturer", equipment.manufacturer)}
        ${eqField("Vendor", equipment.vendor)}
        ${eqField("Serial Number", equipment.serial_number)}
        ${eqField("Asset Number", equipment.asset_number)}
        ${eqField("Department", equipment.department)}
        ${eqField("Criticality", equipment.criticality)}
        ${eqField("GMP Impact", equipment.gmp_impact)}
      </div>
      ${equipment.notes ? `<div style="margin-top:20px"><label style="display:block;font-size:10.5px;font-weight:700;text-transform:uppercase;color:var(--text-muted);margin-bottom:4px">Notes</label><p style="font-size:13px;color:var(--text);white-space:pre-wrap">${eqEsc(equipment.notes)}</p></div>` : ""}
    `;
  } else if (eqActiveTab === "specifications") {
    el.innerHTML = `
      <div class="eq-form-section-label">Basic Information</div>
      <div class="eq-detail-grid">
        ${eqField("Equipment Name", equipment.name)}
        ${eqField("Equipment Category", equipment.category)}
        ${eqField("Equipment Type", equipment.equipment_type)}
        ${eqField("Equipment Tag Number", equipment.tag_number)}
        ${eqField("Equipment Model", equipment.model)}
        ${eqField("Manufacturer", equipment.manufacturer)}
        ${eqField("Vendor", equipment.vendor)}
        ${eqField("Serial Number", equipment.serial_number)}
        ${eqField("Asset Number", equipment.asset_number)}
      </div>
      <div class="eq-form-section-label">Installation Information</div>
      <div class="eq-detail-grid">
        ${eqField("Plant", equipment.plant)}
        ${eqField("Block", equipment.block)}
        ${eqField("Department", equipment.department)}
        ${eqField("Area", equipment.area)}
        ${eqField("Room", equipment.room)}
        ${eqField("Line", equipment.line)}
        ${eqField("Installation Date", equipment.installation_date)}
        ${eqField("Commissioning Date", equipment.commissioning_date)}
      </div>
    `;
  } else if (eqActiveTab === "qualification") {
    el.innerHTML = `
      <div class="eq-detail-grid">
        ${eqField("Qualification Status", equipment.qualification_status)}
        ${eqField("Validation Status", equipment.validation_status)}
        ${eqField("Qualification Type", equipment.qualification_type)}
        ${eqField("Criticality", equipment.criticality)}
        ${eqField("GMP Impact", equipment.gmp_impact)}
      </div>
      <p style="margin-top:18px;font-size:12px;color:var(--text-muted)">
        Edit these fields from the Equipment list (Edit button). Future Qualification/Validation
        modules (DQ/IQ/OQ/PQ workflows) will update this tab automatically once they reference
        Equipment directly.
      </p>
    `;
  } else if (eqActiveTab === "documentation") {
    await eqRenderDocumentationTab(equipment);
  } else if (eqActiveTab === "validation-history") {
    await eqRenderValidationHistoryTab(equipment);
  } else if (eqActiveTab === "related-documents") {
    el.innerHTML = `
      <div class="eq-empty" style="padding:32px 0">
        <span class='icon' data-lucide='folder-open' style="width:32px;height:32px;opacity:0.5"></span>
        <p>Documents linked specifically to this Equipment appear under the <b>Documentation</b> tab.</p>
        <p style="font-size:12px">General project files remain available in <b>Project Documents</b>.</p>
      </div>`;
  } else if (eqActiveTab === "related-risk") {
    el.innerHTML = `
      <div class="eq-empty" style="padding:32px 0">
        <span class='icon' data-lucide='shield-alert' style="width:32px;height:32px;opacity:0.5"></span>
        <p>No linked Risk Assessments yet.</p>
        <p style="font-size:12px">The Risk Management Suite does not reference Equipment directly yet —
        this tab will populate automatically once that integration is built.</p>
      </div>`;
  } else if (eqActiveTab === "future") {
    el.innerHTML = `
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:16px">
        These modules are planned on top of this Equipment record's architecture — not built yet.
      </p>
      <div class="eq-future-grid">
        ${EQ_FUTURE_MODULES.map(m => `
          <div class="eq-future-card">
            <span class='icon' data-lucide='${m.icon}'></span>
            <div class="eq-future-card-name">${m.name}</div>
            <div class="eq-future-card-tag">Planned</div>
          </div>`).join("")}
      </div>`;
  }
}

async function eqRenderDocumentationTab(equipment) {
  const el = document.getElementById("eq-profile-body");
  el.innerHTML = `
    <div style="display:flex;justify-content:flex-end;margin-bottom:14px">
      <button class="btn-secondary" id="eq-link-doc-btn"><span class='icon' data-lucide='link'></span> Link Document</button>
    </div>
    <div id="eq-doc-groups">Loading…</div>
  `;
  document.getElementById("eq-link-doc-btn").addEventListener("click", () => eqOpenLinkDocModal(equipment.id));

  try {
    const res = await fetch(`/equipment/${equipment.id}/documents`);
    const links = await res.json();
    const groupsEl = document.getElementById("eq-doc-groups");

    if (!links.length) {
      groupsEl.innerHTML = `<div class="eq-empty" style="padding:32px 0">
        <span class='icon' data-lucide='paperclip' style="width:28px;height:28px;opacity:0.5"></span>
        <p>No documents linked yet. Link a User Manual, SOP, Drawing, or other reference from the
        Knowledge Base or this Project's Documents — nothing is duplicated.</p>
      </div>`;
      if (window.refreshIcons) window.refreshIcons();
      return;
    }

    const byRole = {};
    links.forEach(l => { (byRole[l.document_role] = byRole[l.document_role] || []).push(l); });

    groupsEl.innerHTML = Object.keys(byRole).map(role => `
      <div class="eq-doc-role-group">
        <div class="eq-doc-role-title">${EQ_DOC_ROLE_LABELS[role] || role}</div>
        ${byRole[role].map(l => `
          <div class="eq-doc-item ${l.resolved ? "" : "eq-doc-broken"}">
            <div class="eq-doc-item-title">
              <span class='icon' data-lucide='${l.source_type === "kb" ? "library" : "file-text"}'></span>
              <span>${eqEsc(l.display_title)}</span>
              <span style="font-size:10.5px;color:var(--text-disabled)">${l.source_type === "kb" ? "Knowledge Base" : "Project Document"}</span>
            </div>
            <button class="eq-row-actions eq-btn-danger" style="border:none;background:none;cursor:pointer" data-id="${l.id}" title="Unlink">
              <span class='icon' data-lucide='x'></span>
            </button>
          </div>
        `).join("")}
      </div>
    `).join("");

    groupsEl.querySelectorAll("button[data-id]").forEach(btn => {
      btn.addEventListener("click", async () => {
        await fetch(`/equipment/${equipment.id}/documents/${btn.dataset.id}`, { method: "DELETE" });
        eqRenderDocumentationTab(equipment);
      });
    });
    if (window.refreshIcons) window.refreshIcons();
  } catch {
    document.getElementById("eq-doc-groups").innerHTML =
      '<p style="color:var(--text-muted);font-size:13px">Could not load linked documents.</p>';
  }
}

async function eqRenderValidationHistoryTab(equipment) {
  const el = document.getElementById("eq-profile-body");
  el.innerHTML = "Loading…";
  try {
    const res = await fetch(`/equipment/${equipment.id}/ai-context`);
    const bundle = await res.json();
    const history = bundle.validation_history || [];

    if (!history.length) {
      el.innerHTML = `<div class="eq-empty" style="padding:32px 0">
        <span class='icon' data-lucide='history' style="width:28px;height:28px;opacity:0.5"></span>
        <p>No validation documents generated for this project yet.</p>
        <p style="font-size:12px">Shown here: this project's Generate Document history
        (approximate — precise per-equipment linkage is a future enhancement).</p>
      </div>`;
      if (window.refreshIcons) window.refreshIcons();
      return;
    }

    el.innerHTML = `
      <table class="qms-table">
        <thead><tr><th>Type</th><th>Title</th><th>Created</th></tr></thead>
        <tbody>
          ${history.map(h => `<tr><td>${eqEsc(h.doc_type)}</td><td>${eqEsc(h.title)}</td><td>${new Date(h.created_at).toLocaleDateString()}</td></tr>`).join("")}
        </tbody>
      </table>
    `;
  } catch {
    el.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Could not load validation history.</p>';
  }
}

// ── Link Document modal ───────────────────────────────────────────────────────

async function eqOpenLinkDocModal(equipmentId) {
  const modal = document.getElementById("eq-link-doc-modal");
  const overlay = document.getElementById("eq-link-doc-overlay");
  document.getElementById("eq-link-doc-form").reset();
  document.getElementById("eq-link-doc-equipment-id").value = equipmentId;
  await eqRefreshLinkDocSourceList();
  modal.classList.add("open");
  overlay.classList.add("open");
}

function eqCloseLinkDocModal() {
  document.getElementById("eq-link-doc-modal").classList.remove("open");
  document.getElementById("eq-link-doc-overlay").classList.remove("open");
}
window.eqCloseLinkDocModal = eqCloseLinkDocModal;

async function eqRefreshLinkDocSourceList() {
  const sourceType = document.getElementById("eq-link-source-type").value;
  const select = document.getElementById("eq-link-source-id");
  select.innerHTML = '<option value="">Loading…</option>';

  try {
    if (sourceType === "kb") {
      const res = await fetch("/kb/documents");
      const docs = await res.json();
      select.innerHTML = docs.map(d => `<option value="${d.id}">${eqEsc(d.title)} (${d.file_type})</option>`).join("")
        || '<option value="">No Knowledge Base documents yet</option>';
    } else {
      if (!window.activeProject) { select.innerHTML = '<option value="">No project selected</option>'; return; }
      const res = await fetch(`/projects/${window.activeProject.id}/documents`);
      const docs = await res.json();
      select.innerHTML = docs.map(d => `<option value="${d.id}">${eqEsc(d.original_name)} (${d.file_type})</option>`).join("")
        || '<option value="">No project documents yet</option>';
    }
  } catch {
    select.innerHTML = '<option value="">Could not load documents</option>';
  }
}

async function eqSubmitLinkDoc(e) {
  e.preventDefault();
  const equipmentId = document.getElementById("eq-link-doc-equipment-id").value;
  const payload = {
    document_role: document.getElementById("eq-link-role").value,
    source_type: document.getElementById("eq-link-source-type").value,
    source_id: parseInt(document.getElementById("eq-link-source-id").value, 10),
  };
  if (!payload.source_id) { alert("Please select a document."); return; }

  try {
    const res = await fetch(`/equipment/${equipmentId}/documents`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (!res.ok) { const err = await res.json(); throw new Error(err.error || "Failed"); }
    eqCloseLinkDocModal();
    eqRenderDocumentationTab({ id: equipmentId });
  } catch (err) {
    alert(err.message || "Could not link document. Please try again.");
  }
}

// ── Utility ───────────────────────────────────────────────────────────────────

function eqEsc(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── Wire up static DOM elements (modals, forms) ───────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const addBtn        = document.getElementById("eq-add-btn");
  const modalOverlay  = document.getElementById("eq-modal-overlay");
  const modalClose    = document.getElementById("eq-modal-close");
  const modalCancel   = document.getElementById("eq-modal-cancel");
  const form          = document.getElementById("eq-form");

  if (addBtn) addBtn.addEventListener("click", () => eqOpenModal(null));
  if (modalOverlay) modalOverlay.addEventListener("click", eqCloseModal);
  if (modalClose) modalClose.addEventListener("click", eqCloseModal);
  if (modalCancel) modalCancel.addEventListener("click", eqCloseModal);
  if (form) form.addEventListener("submit", eqSubmitForm);

  const linkOverlay = document.getElementById("eq-link-doc-overlay");
  const linkClose   = document.getElementById("eq-link-doc-close");
  const linkCancel  = document.getElementById("eq-link-doc-cancel");
  const linkForm    = document.getElementById("eq-link-doc-form");
  const linkSourceType = document.getElementById("eq-link-source-type");

  if (linkOverlay) linkOverlay.addEventListener("click", eqCloseLinkDocModal);
  if (linkClose) linkClose.addEventListener("click", eqCloseLinkDocModal);
  if (linkCancel) linkCancel.addEventListener("click", eqCloseLinkDocModal);
  if (linkForm) linkForm.addEventListener("submit", eqSubmitLinkDoc);
  if (linkSourceType) linkSourceType.addEventListener("change", eqRefreshLinkDocSourceList);

  const backBtn = document.getElementById("eq-profile-back-btn");
  if (backBtn) backBtn.addEventListener("click", eqBackToList);
});

// ── Expose for view-switch wiring and inline handlers ─────────────────────────
window.loadEquipment = eqLoadList;
window.eqOpenModal = eqOpenModal;
window.eqOpenProfile = eqOpenProfile;
