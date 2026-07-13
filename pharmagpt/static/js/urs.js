/**
 * urs.js — URS Management Suite frontend.
 *
 * Views:
 *   urs-dashboard   : Stats overview + recent URS list
 *   urs-list        : Full URS list with search/filter
 *   urs-new         : 5-step wizard to create a new URS
 *   urs-detail      : Single URS view with tabs (Overview, Requirements, Review, Approval, Versions, Traceability)
 */

/* ── State ─────────────────────────────────────────────────────────────────── */
let ursState = {
  currentURS: null,
  requirements: [],
  wizardStep: 1,
  wizardData: {},
  selectedCategory: null,
  selectedEquipmentType: null,
  generating: false,
  activeDetailTab: "overview",
};

/* ── Category definitions ───────────────────────────────────────────────────── */
const URS_CATEGORIES = [
  {
    key: "manufacturing",
    name: "Manufacturing Equipment",
    icon: "<span class=\'icon\' data-lucide=\'settings\'></span>",
    sub: "Compression, Coating, Granulation…",
    types: [
      ["tablet_compression",  "Tablet Compression Machine"],
      ["capsule_filling",     "Capsule Filling Machine"],
      ["coating_machine",     "Coating Machine"],
      ["granulation",         "Granulation (RMG/HSG)"],
      ["blending",            "Blending / IBC Blender"],
      ["drying",              "Drying (Tray/Tunnel)"],
      ["fluid_bed_processor", "Fluid Bed Processor"],
      ["milling",             "Milling Machine"],
      ["sifter",              "Vibro Sifter"],
      ["ibc",                 "Intermediate Bulk Container (IBC)"],
    ],
  },
  {
    key: "packaging",
    name: "Packaging Equipment",
    icon: "<span class=\'icon\' data-lucide=\'package\'></span>",
    sub: "Blister, Filling, Labeling…",
    types: [
      ["blister_machine",       "Blister Machine"],
      ["bottle_filling",        "Bottle Filling Line"],
      ["bottle_packing",        "Bottle Packing Line"],
      ["cartoner",              "Cartoner"],
      ["checkweigher",          "Checkweigher"],
      ["metal_detector",        "Metal Detector"],
      ["vision_inspection",     "Vision Inspection System"],
      ["labeling_machine",      "Labeling Machine"],
      ["serialization_machine", "Serialization Machine"],
      ["case_packer",           "Case Packer"],
      ["palletizer",            "Palletizer"],
      ["induction_sealer",      "Induction Sealer"],
      ["capper",                "Capper"],
    ],
  },
  {
    key: "laboratory",
    name: "Laboratory Equipment",
    icon: "<span class=\'icon\' data-lucide=\'microscope\'></span>",
    sub: "HPLC, GC, Dissolution…",
    types: [
      ["hplc",              "HPLC System"],
      ["gc",                "Gas Chromatograph (GC)"],
      ["uv_spectrophotometer", "UV Spectrophotometer"],
      ["dissolution",       "Dissolution Apparatus"],
      ["balances",          "Analytical/Precision Balance"],
      ["ph_meter",          "pH Meter"],
      ["karl_fischer",      "Karl Fischer Titrator"],
      ["stability_chamber", "Stability Chamber"],
      ["incubator",         "Incubator / BOD Oven"],
      ["autoclave",         "Autoclave / Steam Sterilizer"],
      ["particle_counter",  "Particle Counter"],
    ],
  },
  {
    key: "utilities",
    name: "Utilities",
    icon: "<span class=\'icon\' data-lucide=\'droplet\'></span>",
    sub: "Water, Air, Steam…",
    types: [
      ["purified_water",  "Purified Water (PW) System"],
      ["wfi",             "Water for Injection (WFI)"],
      ["clean_steam",     "Clean Steam Generator"],
      ["compressed_air",  "Compressed Air System"],
      ["nitrogen",        "Nitrogen Generation System"],
      ["vacuum",          "Vacuum System"],
      ["boiler",          "Boiler / Steam Generator"],
      ["chiller",         "Chiller / Cooling System"],
    ],
  },
  {
    key: "hvac",
    name: "HVAC Systems",
    icon: "<span class=\'icon\' data-lucide=\'wind\'></span>",
    sub: "AHU, BMS, Environmental…",
    types: [
      ["hvac_ahu",        "Air Handling Unit (AHU)"],
      ["bms_hvac",        "Building Management System (BMS) – HVAC"],
      ["dp_system",       "Differential Pressure Monitoring System"],
      ["temp_monitoring", "Temperature Monitoring System"],
      ["rh_monitoring",   "Humidity Monitoring System"],
      ["hepa_system",     "HEPA Filtration System"],
      ["env_monitoring",  "Environmental Monitoring System"],
    ],
  },
  {
    key: "computerized",
    name: "Computerized Systems",
    icon: "<span class=\'icon\' data-lucide=\'laptop\'></span>",
    sub: "SCADA, MES, LIMS, ERP…",
    types: [
      ["scada",                "SCADA System"],
      ["bms",                  "Building Management System (BMS)"],
      ["mes",                  "Manufacturing Execution System (MES)"],
      ["lims",                 "Laboratory Information Management System (LIMS)"],
      ["ebr",                  "Electronic Batch Record (EBR)"],
      ["erp",                  "Enterprise Resource Planning (ERP)"],
      ["barcode_system",       "Barcode System"],
      ["serialization_system", "Serialization System"],
      ["data_historian",       "Data Historian"],
      ["electronic_logbook",   "Electronic Logbook"],
      ["plc_system",           "PLC System"],
      ["hmi_system",           "HMI System"],
      ["recipe_management",    "Recipe Management System"],
      ["iot_platform",         "Industrial IoT Platform"],
      ["cloud_system",         "Cloud Validation System"],
      ["ai_application",       "AI Application"],
    ],
  },
  {
    key: "warehouse",
    name: "Warehouse / Storage",
    icon: "<span class=\'icon\' data-lucide=\'factory\'></span>",
    sub: "Cold Room, Racking, RFID…",
    types: [
      ["cold_room",          "Cold Room / Cold Storage"],
      ["racking_system",     "Racking System"],
      ["dispensing_booth",   "Dispensing Booth"],
      ["sampling_booth",     "Sampling Booth"],
      ["warehouse_automation","Warehouse Automation System"],
      ["rfid_system",        "RFID System"],
    ],
  },
  {
    key: "miscellaneous",
    name: "Miscellaneous",
    icon: "<span class=\'icon\' data-lucide=\'wrench\'></span>",
    sub: "Custom equipment or system",
    types: [
      ["custom", "Custom Equipment / System"],
    ],
  },
];

const REQUIREMENT_SECTIONS = [
  "General Requirements",
  "Functional Requirements",
  "Operational Requirements",
  "Performance Requirements",
  "Process Requirements",
  "Safety Requirements",
  "GMP Requirements",
  "Regulatory Requirements",
  "Data Integrity Requirements",
  "Alarm Requirements",
  "Security Requirements",
  "Access Control",
  "Audit Trail",
  "Electronic Records",
  "Electronic Signature",
  "Reporting",
  "Communication & Networking",
  "Backup & Recovery",
  "Maintenance & Calibration",
  "Environmental Conditions",
  "Cleaning Requirements",
  "Documentation",
  "Utilities",
  "Cybersecurity",
  "Custom Requirements",
];

/* ── Init ───────────────────────────────────────────────────────────────────── */
window.initURS = function () {
  showView("view-urs-dashboard");
  loadURSDashboard();
};

function showView(viewId) {
  document.querySelectorAll("main[id]").forEach(m => {
    m.style.display = "none";
  });
  const el = document.getElementById(viewId);
  if (el) el.style.display = "flex";
}

/* ── Notification System ───────────────────────────────────────────────────
   Stacked, top-right notifications. success/info auto-dismiss; warning/error
   persist until the user dismisses or retries them — nothing disappears out
   from under a user who hasn't read it yet. Errors get a short client-side
   correlation ID and a "Copy Details" action so there's something concrete
   to hand to support; there is no server-issued error ID (frontend-only
   scope this iteration), so this identifies the *occurrence* client-side,
   not a server log record.
──────────────────────────────────────────────────────────────────────────── */
const URS_NOTIFY_ICONS = {
  success: "<span class='icon' data-lucide='check-circle-2'></span>",
  warning: "<span class='icon' data-lucide='alert-triangle'></span>",
  error:   "<span class='icon' data-lucide='x-circle'></span>",
  info:    "<span class='icon' data-lucide='info'></span>",
};

function ursNotifyStack() {
  let stack = document.getElementById("urs-notify-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.id = "urs-notify-stack";
    stack.className = "urs-notify-stack";
    document.body.appendChild(stack);
  }
  return stack;
}

function ursGenErrorId() {
  return "ERR-" + Date.now().toString(36).toUpperCase() + "-" + Math.random().toString(36).slice(2, 6).toUpperCase();
}

/**
 * ursNotify({ type, title, message, detail, retry, category, persistent })
 *   type: "success" | "warning" | "error" | "info" (default "info")
 *   retry: optional async function — adds a Retry button that re-invokes it
 *   detail: optional extra text (e.g. raw server error) for "Copy Details"
 *   category: optional short label (Authentication/Validation/Generation/…)
 *   persistent: force no auto-dismiss regardless of type
 * Returns { dismiss } so callers can close it programmatically.
 */
function ursNotify(opts) {
  const { type = "info", title, message, detail, retry, category, persistent } = opts || {};
  const stack = ursNotifyStack();
  const el = document.createElement("div");
  el.className = `urs-notify ${type}`;
  const isPersistent = persistent || type === "error" || type === "warning";
  const errorId = type === "error" ? ursGenErrorId() : null;

  el.innerHTML = `
    <div class="urs-notify-icon">${URS_NOTIFY_ICONS[type] || URS_NOTIFY_ICONS.info}</div>
    <div class="urs-notify-body">
      ${title ? `<div class="urs-notify-title">${escHtml(title)}${category ? ` <span style="font-weight:500;color:var(--text-muted)">· ${escHtml(category)}</span>` : ""}</div>` : ""}
      <div class="urs-notify-message">${escHtml(message || "")}</div>
      ${errorId ? `<div class="urs-notify-id">Error ID: ${errorId}</div>` : ""}
      <div class="urs-notify-actions"></div>
    </div>
    <button class="urs-notify-close" aria-label="Dismiss">&times;</button>`;

  const actions = el.querySelector(".urs-notify-actions");
  const dismiss = () => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 220);
  };
  el.querySelector(".urs-notify-close").onclick = dismiss;

  if (retry) {
    const retryBtn = document.createElement("button");
    retryBtn.className = "urs-notify-btn primary";
    retryBtn.textContent = "Retry";
    retryBtn.onclick = async () => {
      retryBtn.disabled = true;
      retryBtn.textContent = "Retrying…";
      dismiss();
      try { await retry(); } catch (e) { /* retry() is expected to notify on its own failure */ }
    };
    actions.appendChild(retryBtn);
  }
  if (detail) {
    const copyBtn = document.createElement("button");
    copyBtn.className = "urs-notify-btn";
    copyBtn.textContent = "Copy Details";
    copyBtn.onclick = async () => {
      const text = `${title || ""}\n${message || ""}\n${detail}${errorId ? `\nError ID: ${errorId}` : ""}`.trim();
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.textContent = "Copied!";
        setTimeout(() => { copyBtn.textContent = "Copy Details"; }, 1500);
      } catch (e) { /* clipboard unavailable — no-op, not worth surfacing */ }
    };
    actions.appendChild(copyBtn);
  }
  const dismissBtn = document.createElement("button");
  dismissBtn.className = "urs-notify-btn";
  dismissBtn.textContent = "Dismiss";
  dismissBtn.onclick = dismiss;
  actions.appendChild(dismissBtn);

  stack.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));

  if (!isPersistent) {
    setTimeout(dismiss, type === "success" ? 3500 : 4500);
  }
  return { dismiss };
}

// Backward-compatible wrapper — every existing ursToast(msg, type) call site
// (there are ~20 across this file) now renders through the stacked
// notification system automatically, with no per-call-site changes needed.
function ursToast(msg, type = "info") {
  ursNotify({ type, message: msg });
}

/* ─────────────────────────────────────────────────────────────────────────────
   DASHBOARD
────────────────────────────────────────────────────────────────────────────── */
window.loadURSDashboard = async function () {
  showView("view-urs-dashboard");
  const body = document.getElementById("urs-dash-body");
  if (!body) return;
  body.innerHTML = ursDashboardSkeleton();

  try {
    const [statsResp, listResp] = await Promise.all([fetch("/urs/dashboard"), fetch("/urs/")]);
    if (!statsResp.ok) throw new Error(`Dashboard stats request failed (HTTP ${statsResp.status})`);
    if (!listResp.ok) throw new Error(`URS list request failed (HTTP ${listResp.status})`);
    const [stats, allURS] = await Promise.all([statsResp.json(), listResp.json()]);
    body.innerHTML = buildDashboardHTML(stats, allURS);
  } catch (e) {
    body.innerHTML = ursErrorStateHTML("Couldn't load the dashboard", e.message, "loadURSDashboard()");
    ursNotify({
      type: "error", title: "Dashboard failed to load", message: e.message,
      category: "Database", retry: () => loadURSDashboard(),
    });
  }
};

function ursDashboardSkeleton() {
  return `
  <div class="urs-dash-stats">
    ${Array(6).fill('<div class="urs-skeleton urs-skeleton-stat"></div>').join("")}
  </div>
  <div class="urs-dash-grid">
    <div class="urs-dash-card"><div class="urs-dash-card-body" style="padding-top:16px">
      ${Array(3).fill('<div class="urs-skeleton urs-skeleton-card"></div>').join("")}
    </div></div>
    <div class="urs-dash-card"><div class="urs-dash-card-body" style="padding-top:16px">
      ${Array(4).fill('<div class="urs-skeleton urs-skeleton-line" style="width:88%"></div>').join("")}
    </div></div>
  </div>`;
}

/* Shared retry-capable error state markup for any panel that failed to load.
   `retryExpr` is a literal JS expression string (e.g. "loadURSDashboard()")
   invoked by the Retry button's onclick — kept as a string rather than a
   function reference so this can be safely embedded via innerHTML. */
function ursErrorStateHTML(title, message, retryExpr) {
  return `<div class="urs-error-state">
    <div class="urs-empty-icon"><span class='icon' data-lucide='alert-triangle'></span></div>
    <div class="urs-empty-title">${escHtml(title)}</div>
    <div class="urs-empty-sub">${escHtml(message)}</div>
    ${retryExpr ? `<button class="btn-urs-primary" style="margin-top:14px" onclick="${retryExpr}"><span class='icon' data-lucide='refresh-cw'></span> Retry</button>` : ""}
  </div>`;
}

function buildDashboardHTML(stats, allURS) {
  const categoryColors = {
    manufacturing: "#8A6B52", packaging: "#5F8A61", laboratory: "#8A6B52",
    utilities: "#5F8A61", hvac: "#A97D2E", computerized: "#A8544F",
    warehouse: "#8A6B52", miscellaneous: "#66615B",
  };

  let html = `
  <div class="urs-dash-stats">
    <div class="urs-stat-card">
      <div class="urs-stat-value">${stats.total || 0}</div>
      <div class="urs-stat-label">Total URS</div>
    </div>
    <div class="urs-stat-card stat-draft">
      <div class="urs-stat-value">${stats.draft || 0}</div>
      <div class="urs-stat-label">Draft</div>
    </div>
    <div class="urs-stat-card stat-review">
      <div class="urs-stat-value">${stats.under_review || 0}</div>
      <div class="urs-stat-label">Under Review</div>
    </div>
    <div class="urs-stat-card stat-approved">
      <div class="urs-stat-value">${stats.approved || 0}</div>
      <div class="urs-stat-label">Approved</div>
    </div>
    <div class="urs-stat-card stat-obsolete">
      <div class="urs-stat-value">${stats.pending_approval || 0}</div>
      <div class="urs-stat-label">Pending Approval</div>
    </div>
    <div class="urs-stat-card">
      <div class="urs-stat-value">${stats.total_requirements || 0}</div>
      <div class="urs-stat-label">Total Requirements</div>
    </div>
  </div>
  <div class="urs-dash-grid">
    <div class="urs-dash-card">
      <div class="urs-dash-card-header">
        <span class="urs-dash-card-title">Recent URS Documents</span>
        <button class="btn-urs-outline" onclick="loadURSList()">View All</button>
      </div>
      <div class="urs-dash-card-body">`;

  if (!allURS.length) {
    html += `<div class="urs-empty" style="padding:30px">
      <div class="urs-empty-icon"><span class=\'icon\' data-lucide=\'clipboard-list\'></span></div>
      <p>No URS documents yet.</p>
      <button class="btn-urs-primary" style="margin-top:12px" onclick="startNewURS()"><span class=\'icon\' data-lucide=\'plus\'></span> Create First URS</button>
    </div>`;
  } else {
    allURS.slice(0, 6).forEach(u => {
      html += `<div class="urs-card status-${u.status}" onclick="openURS(${u.id})" style="margin-bottom:12px;cursor:pointer">
        <div class="urs-card-number">${u.urs_number || "—"}</div>
        <div class="urs-card-title">${escHtml(u.title)}</div>
        <div class="urs-card-equipment">${escHtml(u.equipment_name || "—")}</div>
        <div class="urs-card-tags">
          <span class="urs-tag urs-tag-status ${u.status}">${formatStatus(u.status)}</span>
          ${u.category ? `<span class="urs-tag urs-tag-category">${u.category}</span>` : ""}
        </div>
        <div class="urs-card-meta">
          <span>${u.department || "—"}</span>
          <span>${formatDate(u.created_at)}</span>
        </div>
      </div>`;
    });
  }

  html += `</div></div>
    <div class="urs-dash-card">
      <div class="urs-dash-card-header">
        <span class="urs-dash-card-title">Requirements by Category</span>
      </div>
      <div class="urs-dash-card-body">`;

  const byCategory = stats.by_category || {};
  if (Object.keys(byCategory).length) {
    Object.entries(byCategory).forEach(([cat, count]) => {
      const color = categoryColors[cat] || "#9A948C";
      html += `<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
        <div style="width:12px;height:12px;border-radius:50%;background:${color};flex-shrink:0"></div>
        <div style="flex:1;font-size:13px;color:var(--text)">${cat.replace(/_/g,' ')}</div>
        <div style="font-size:13px;font-weight:700;color:var(--navy)">${count}</div>
        <div style="width:80px;height:6px;background:var(--border);border-radius:3px;overflow:hidden">
          <div style="height:100%;width:${Math.min(100,(count/stats.total)*100)}%;background:${color};border-radius:3px"></div>
        </div>
      </div>`;
    });
  } else {
    html += `<p style="font-size:13px;color:var(--text-muted)">No data yet.</p>`;
  }

  html += `</div></div>
    <div class="urs-dash-card" style="grid-column:1/-1">
      <div class="urs-dash-card-header">
        <span class="urs-dash-card-title">Quick Actions</span>
      </div>
      <div class="urs-dash-card-body" style="display:flex;gap:12px;flex-wrap:wrap">
        <button class="btn-urs-primary" onclick="startNewURS()"><span class=\'icon\' data-lucide=\'plus\'></span> New URS</button>
        <button class="btn-urs-outline" onclick="loadURSList()"><span class=\'icon\' data-lucide=\'clipboard-list\'></span> All URS Documents</button>
        <button class="btn-urs-outline" onclick="showURSApprovalQueue()"><span class=\'icon\' data-lucide=\'check-circle-2\'></span> Approval Queue</button>
      </div>
    </div>
  </div>`;

  return html;
}

/* ─────────────────────────────────────────────────────────────────────────────
   URS LIST
────────────────────────────────────────────────────────────────────────────── */
window.loadURSList = function () {
  showView("view-urs-list");
  fetchAndRenderURSList();
};

async function fetchAndRenderURSList(filters = {}) {
  ursState.lastListFilters = filters;
  const grid = document.getElementById("urs-list-grid");
  const empty = document.getElementById("urs-list-empty");
  if (!grid) return;
  if (empty) empty.style.display = "none";
  grid.innerHTML = Array(6).fill('<div class="urs-skeleton urs-skeleton-card"></div>').join("");

  const params = new URLSearchParams(filters);
  try {
    const resp = await fetch(`/urs/?${params}`);
    if (!resp.ok) throw new Error(`Server returned HTTP ${resp.status}`);
    const data = await resp.json();
    grid.innerHTML = "";
    if (!data.length) {
      if (empty) empty.style.display = "flex";
      return;
    }
    data.forEach(u => {
      const card = document.createElement("div");
      card.className = `urs-card status-${u.status}`;
      card.innerHTML = `
        <div class="urs-card-number">${escHtml(u.urs_number || "—")}</div>
        <div class="urs-card-title">${escHtml(u.title)}</div>
        <div class="urs-card-equipment"><span class=\'icon\' data-lucide=\'package\'></span> ${escHtml(u.equipment_name || "Not specified")}</div>
        <div class="urs-card-tags">
          <span class="urs-tag urs-tag-status ${u.status}">${formatStatus(u.status)}</span>
          ${u.category ? `<span class="urs-tag urs-tag-category">${u.category}</span>` : ""}
          ${u.revision ? `<span class="urs-tag" style="background:#F1ECE6;color:#66615B">Rev ${u.revision}</span>` : ""}
        </div>
        <div class="urs-card-meta">
          <span><span class=\'icon\' data-lucide=\'user\'></span> ${escHtml(u.prepared_by || "—")}</span>
          <span><span class=\'icon\' data-lucide=\'calendar\'></span> ${formatDate(u.created_at)}</span>
        </div>
        <div class="urs-card-actions">
          <button class="btn-urs-outline" onclick="event.stopPropagation();openURS(${u.id})"><span class=\'icon\' data-lucide=\'folder-open\'></span> Open</button>
          <button class="btn-urs-outline urs-export-btn" data-export-state="idle" onclick="event.stopPropagation();exportURSDocx(${u.id}, '${escHtml(u.urs_number || 'URS')}', this)">
            <div class="urs-btn-spinner"></div><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span>
            <span class="urs-btn-label-idle">DOCX</span><span class="urs-btn-label-busy">Preparing…</span><span class="urs-btn-label-done">Done</span>
          </button>
          <button class="btn-urs-danger" onclick="event.stopPropagation();deleteURS(${u.id})"><span class=\'icon\' data-lucide=\'trash-2\'></span></button>
        </div>`;
      card.addEventListener("click", () => openURS(u.id));
      grid.appendChild(card);
    });
  } catch (e) {
    grid.innerHTML = "";
    if (empty) empty.style.display = "none";
    grid.insertAdjacentHTML("beforeend", ursErrorStateHTML(
      "Couldn't load URS documents", e.message, "fetchAndRenderURSList(ursState.lastListFilters)",
    ));
    ursNotify({
      type: "error", title: "URS list failed to load", message: e.message,
      category: "Database", retry: () => fetchAndRenderURSList(filters),
    });
  }
}

window.applyURSFilters = function () {
  const q = document.getElementById("urs-search-input")?.value || "";
  const status = document.getElementById("urs-filter-status")?.value || "";
  const category = document.getElementById("urs-filter-category")?.value || "";
  fetchAndRenderURSList({ q, status, category });
};

/* ─────────────────────────────────────────────────────────────────────────────
   NEW URS WIZARD  (5 steps)
   Step 1: Category + Equipment Type
   Step 2: Project Information
   Step 3: AI Generation Options
   Step 4: Requirements Editor
   Step 5: Approval
────────────────────────────────────────────────────────────────────────────── */
window.startNewURS = function () {
  ursState.wizardStep = 1;
  ursState.wizardData = {};
  ursState.selectedCategory = null;
  ursState.selectedEquipmentType = null;
  ursState.currentURS = null;
  ursState.requirements = [];
  showView("view-urs-new");
  renderWizardStep(1);
};

function renderWizardStep(step) {
  updateWizardStepUI(step);
  const body = document.getElementById("urs-wizard-body");
  if (!body) return;
  body.innerHTML = "";

  if (step === 1) renderStep1(body);
  else if (step === 2) renderStep2(body);
  else if (step === 3) renderStep3(body);
  else if (step === 4) renderStep4(body);
  else if (step === 5) renderStep5(body);
}

function updateWizardStepUI(step) {
  for (let i = 1; i <= 5; i++) {
    const dot = document.getElementById(`urs-step-dot-${i}`);
    const lbl = document.getElementById(`urs-step-lbl-${i}`);
    const line = document.getElementById(`urs-step-line-${i}`);
    if (!dot) continue;
    dot.className = "urs-step-dot" + (i < step ? " done" : i === step ? " active" : "");
    if (lbl) lbl.className = "urs-step-label" + (i < step ? " done" : i === step ? " active" : "");
    if (line) line.className = "urs-step-line" + (i < step ? " done" : "");
  }
}

/* ── Step 1: Category & Equipment ─────────────────────────────────────────── */
function renderStep1(body) {
  let html = `<div class="urs-section-header"><div class="section-icon"><span class=\'icon\' data-lucide=\'clipboard-list\'></span></div>Select Equipment / System Category</div>
  <div class="urs-category-grid">`;
  URS_CATEGORIES.forEach(cat => {
    const sel = ursState.selectedCategory === cat.key ? "selected" : "";
    html += `<div class="urs-category-card ${sel}" onclick="selectCategory('${cat.key}')" id="cat-card-${cat.key}">
      <div class="urs-category-icon">${cat.icon}</div>
      <div class="urs-category-name">${cat.name}</div>
      <div class="urs-category-sub">${cat.sub}</div>
    </div>`;
  });
  html += `</div>
  <div id="urs-equip-section" style="display:${ursState.selectedCategory ? 'block' : 'none'}">
    <div class="urs-section-header" style="margin-top:24px"><div class="section-icon"><span class=\'icon\' data-lucide=\'wrench\'></span></div>Select Equipment Type</div>
    <div class="urs-equip-list" id="urs-equip-list"></div>
  </div>
  <div style="display:flex;justify-content:flex-end;margin-top:24px">
    <button class="btn-urs-primary" onclick="wizardNext()" id="step1-next-btn" ${ursState.selectedEquipmentType ? "" : "disabled"}>
      Next: Project Information <span class=\'icon\' data-lucide=\'arrow-right\'></span>
    </button>
  </div>`;
  body.innerHTML = html;
  if (ursState.selectedCategory) renderEquipmentList(ursState.selectedCategory);
}

window.selectCategory = function (catKey) {
  ursState.selectedCategory = catKey;
  ursState.selectedEquipmentType = null;
  document.querySelectorAll(".urs-category-card").forEach(c => c.classList.remove("selected"));
  document.getElementById(`cat-card-${catKey}`)?.classList.add("selected");
  document.getElementById("urs-equip-section").style.display = "block";
  renderEquipmentList(catKey);
  const btn = document.getElementById("step1-next-btn");
  if (btn) btn.disabled = true;
};

function renderEquipmentList(catKey) {
  const cat = URS_CATEGORIES.find(c => c.key === catKey);
  if (!cat) return;
  const list = document.getElementById("urs-equip-list");
  if (!list) return;
  list.innerHTML = "";
  cat.types.forEach(([key, label]) => {
    const item = document.createElement("div");
    item.className = "urs-equip-item" + (ursState.selectedEquipmentType === key ? " selected" : "");
    item.innerHTML = `<span>${label}</span>`;
    item.onclick = () => {
      ursState.selectedEquipmentType = key;
      ursState.wizardData.equipment_type = key;
      ursState.wizardData.category = catKey;
      ursState.wizardData.equipment_name = label;
      document.querySelectorAll(".urs-equip-item").forEach(el => el.classList.remove("selected"));
      item.classList.add("selected");
      const btn = document.getElementById("step1-next-btn");
      if (btn) btn.disabled = false;
    };
    list.appendChild(item);
  });
}

/* ── Step 2: Project Information ───────────────────────────────────────────── */
// URS Number / Document Number / Version / Revision / Prepared By are no
// longer entered here — the backend (Stabilization Iteration 2) auto-issues
// them at creation and ignores client-supplied values for these fields, so
// editable inputs for them would just be misleading. They're shown as
// read-only "system-assigned" fields instead, populated from
// ursState.currentURS once the record exists (blank/placeholder before
// that — the numbers aren't allocated until creation).
function renderStep2(body) {
  const d = ursState.wizardData;
  const urs = ursState.currentURS;
  const preparedByName = (window.PharmaAuth && PharmaAuth.getUser && PharmaAuth.getUser()?.display_name) || "";

  const readonlyField = (label, value, badge) => `
    <div class="urs-field">
      <label class="urs-label">${label}</label>
      <div class="urs-readonly-field">
        <span class="value">${escHtml(value)}</span>
        <span class="urs-readonly-badge">${badge}</span>
      </div>
    </div>`;

  body.innerHTML = `
  <div class="urs-section-header"><div class="section-icon"><span class=\'icon\' data-lucide=\'pencil-line\'></span></div>Project Information</div>

  <div class="urs-doc-control-note">
    <span class="icon" data-lucide="info"></span>
    <div>URS Number, Document Number, Version, Revision, and Prepared By are assigned automatically by the system — they are not entered manually. Reviewed By, Approved By, and QA Approval are captured later, in the Approval step.</div>
  </div>

  <div class="urs-form-grid" style="margin-bottom:20px">
    ${readonlyField("URS Number", urs?.urs_number || "Assigned when this URS is created", "Auto")}
    ${readonlyField("Document Number", urs?.doc_number || "Assigned when this URS is created", "Auto")}
    ${readonlyField("Version", urs?.version || "1.0", "Auto")}
    ${readonlyField("Revision", urs?.revision || "A", "Auto")}
    ${readonlyField("Prepared By", urs?.prepared_by || preparedByName || "Current user", "You")}
  </div>

  <div class="urs-form-grid">
    <div class="urs-field full">
      <label class="urs-label">URS Title <span class="req-star">*</span></label>
      <input class="urs-input" id="w-title" value="${d.title || 'URS – ' + (d.equipment_name || '')}" placeholder="User Requirement Specification for…">
    </div>
    <div class="urs-field">
      <label class="urs-label">Equipment Name <span class="req-star">*</span></label>
      <input class="urs-input" id="w-equipment-name" value="${d.equipment_name || ''}" placeholder="Equipment full name">
    </div>
    <div class="urs-field">
      <label class="urs-label">Equipment ID / Tag</label>
      <input class="urs-input" id="w-equipment-id" value="${d.equipment_id || ''}" placeholder="e.g. TC-01">
    </div>
    <div class="urs-field">
      <label class="urs-label">Manufacturer</label>
      <input class="urs-input" id="w-manufacturer" value="${d.manufacturer || ''}" placeholder="Vendor / Manufacturer">
    </div>
    <div class="urs-field">
      <label class="urs-label">Model Number</label>
      <input class="urs-input" id="w-model" value="${d.model || ''}" placeholder="Model number">
    </div>
    <div class="urs-field">
      <label class="urs-label">Capacity / Scale</label>
      <input class="urs-input" id="w-capacity" value="${d.capacity || ''}" placeholder="e.g. 500 kg/batch">
    </div>
    <div class="urs-field">
      <label class="urs-label">Department</label>
      <input class="urs-input" id="w-department" value="${d.department || ''}" placeholder="e.g. Manufacturing, QC">
    </div>
    <div class="urs-field">
      <label class="urs-label">Site</label>
      <input class="urs-input" id="w-site" value="${d.site || ''}" placeholder="Site / Plant name">
    </div>
    <div class="urs-field">
      <label class="urs-label">Location</label>
      <input class="urs-input" id="w-location" value="${d.location || ''}" placeholder="Room / Area">
    </div>
    <div class="urs-field">
      <label class="urs-label">Validation Type</label>
      <select class="urs-select" id="w-validation-type">
        <option value="">Select…</option>
        <option ${d.validation_type==='IQ/OQ/PQ'?'selected':''}>IQ/OQ/PQ</option>
        <option ${d.validation_type==='CSV'?'selected':''}>CSV</option>
        <option ${d.validation_type==='Process Validation'?'selected':''}>Process Validation</option>
        <option ${d.validation_type==='Cleaning Validation'?'selected':''}>Cleaning Validation</option>
        <option ${d.validation_type==='Computerized System Validation'?'selected':''}>Computerized System Validation</option>
        <option ${d.validation_type==='FAT/SAT'?'selected':''}>FAT/SAT</option>
        <option ${d.validation_type==='Equipment Qualification'?'selected':''}>Equipment Qualification</option>
      </select>
    </div>
    <div class="urs-field full">
      <label class="urs-label">Purpose</label>
      <textarea class="urs-textarea" id="w-purpose" placeholder="Purpose of this URS…">${d.purpose || ''}</textarea>
    </div>
    <div class="urs-field full">
      <label class="urs-label">Intended Use</label>
      <textarea class="urs-textarea" id="w-intended-use" placeholder="Intended use of the equipment / system…">${d.intended_use || ''}</textarea>
    </div>
    <div class="urs-field full">
      <label class="urs-label">Process Description</label>
      <textarea class="urs-textarea" id="w-process-desc" placeholder="Describe the manufacturing or operational process…">${d.process_description || ''}</textarea>
    </div>
  </div>
  <div style="display:flex;justify-content:space-between;margin-top:8px">
    <button class="btn-urs-secondary" style="background:rgba(61,47,33,.06);color:var(--navy);border-color:var(--border)" onclick="wizardBack()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
    <button class="btn-urs-primary" onclick="wizardNext()">Next: Generate Requirements <span class=\'icon\' data-lucide=\'arrow-right\'></span></button>
  </div>`;
}

function collectStep2Data() {
  ursState.wizardData.title          = document.getElementById("w-title")?.value.trim() || "";
  ursState.wizardData.equipment_name = document.getElementById("w-equipment-name")?.value.trim() || "";
  ursState.wizardData.equipment_id   = document.getElementById("w-equipment-id")?.value.trim() || "";
  ursState.wizardData.manufacturer   = document.getElementById("w-manufacturer")?.value.trim() || "";
  ursState.wizardData.model          = document.getElementById("w-model")?.value.trim() || "";
  ursState.wizardData.capacity       = document.getElementById("w-capacity")?.value.trim() || "";
  ursState.wizardData.department     = document.getElementById("w-department")?.value.trim() || "";
  ursState.wizardData.site           = document.getElementById("w-site")?.value.trim() || "";
  ursState.wizardData.location       = document.getElementById("w-location")?.value.trim() || "";
  ursState.wizardData.validation_type= document.getElementById("w-validation-type")?.value || "";
  ursState.wizardData.purpose        = document.getElementById("w-purpose")?.value.trim() || "";
  ursState.wizardData.intended_use   = document.getElementById("w-intended-use")?.value.trim() || "";
  ursState.wizardData.process_description = document.getElementById("w-process-desc")?.value.trim() || "";
}

/* ── Step 3: Generation Options ────────────────────────────────────────────── */
function renderStep3(body) {
  const isComputerized = ["computerized", "hvac"].includes(ursState.wizardData.category);

  const defaultSections = [
    "General Requirements",
    "Functional Requirements",
    "Performance Requirements",
    "Safety Requirements",
    "GMP Requirements",
    "Data Integrity Requirements",
    "Alarm Requirements",
    "Audit Trail",
    ...(isComputerized ? ["Security Requirements", "Electronic Records", "Electronic Signature", "Backup & Recovery", "Cybersecurity"] : []),
  ];

  let sectionsHtml = REQUIREMENT_SECTIONS.map(s => `
    <label class="urs-section-checkbox">
      <input type="checkbox" name="section" value="${s}" ${defaultSections.includes(s) ? "checked" : ""}>
      ${s}
    </label>`).join("");

  body.innerHTML = `
  <div class="urs-section-header"><div class="section-icon"><span class=\'icon\' data-lucide=\'bot\'></span></div>AI Requirement Generation</div>
  <div class="urs-ai-panel">
    <div class="urs-ai-panel-header">
      <div class="urs-ai-icon"><span class=\'icon\' data-lucide=\'sparkles\'></span></div>
      <div>
        <div class="urs-ai-panel-title">AI-Powered Requirement Generation</div>
        <div class="urs-ai-panel-sub">Gemini 2.5 Flash will generate pharmaceutical-grade requirements for: <strong>${escHtml(ursState.wizardData.equipment_name || "the equipment")}</strong></div>
      </div>
    </div>
    <div style="margin-bottom:12px">
      <div class="urs-label" style="margin-bottom:10px">Select Requirement Sections to Generate</div>
      <div class="urs-section-checkboxes">${sectionsHtml}</div>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <button class="btn-urs-primary" onclick="selectAllSections(true)"><span class=\'icon\' data-lucide=\'square-check\'></span> Select All</button>
      <button class="btn-urs-outline" onclick="selectAllSections(false)"><span class=\'icon\' data-lucide=\'square\'></span> Deselect All</button>
    </div>
  </div>

  <div class="urs-ai-panel" style="background:linear-gradient(135deg,#E8F2EA,#E8F2EA);border-color:#E8F2EA">
    <div class="urs-ai-panel-header">
      <div class="urs-ai-icon" style="background:linear-gradient(135deg,#5F8A61,#5F8A61)"><span class=\'icon\' data-lucide=\'book-open\'></span></div>
      <div>
        <div class="urs-ai-panel-title">Requirement Library</div>
        <div class="urs-ai-panel-sub">Load pre-built GMP requirements from the equipment library (instant, no AI needed)</div>
      </div>
    </div>
    <button class="btn-urs-outline" style="border-color:#5F8A61;color:#5F8A61" onclick="loadLibraryRequirements()">
      <span class=\'icon\' data-lucide=\'book-open\'></span> Load Library Requirements for ${escHtml(ursState.wizardData.equipment_name || "this equipment")}
    </button>
  </div>

  <div class="urs-gen-panel" id="urs-gen-progress"></div>

  <div style="display:flex;justify-content:space-between;margin-top:24px">
    <button class="btn-urs-secondary" style="background:rgba(61,47,33,.06);color:var(--navy);border-color:var(--border)" onclick="wizardBack()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
    <div style="display:flex;gap:10px">
      <button class="btn-urs-outline" onclick="skipGeneration()">Skip <span class=\'icon\' data-lucide=\'arrow-right\'></span> Review Requirements</button>
      <button class="btn-urs-primary" id="generate-btn" onclick="runAIGeneration()"><span class=\'icon\' data-lucide=\'sparkles\'></span> Generate with AI <span class=\'icon\' data-lucide=\'arrow-right\'></span></button>
    </div>
  </div>`;
}

window.selectAllSections = function (checked) {
  document.querySelectorAll('input[name="section"]').forEach(cb => cb.checked = checked);
};

window.loadLibraryRequirements = async function () {
  if (!ursState.currentURS) {
    await createURSRecord();
  }
  if (!ursState.currentURS) return;
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = "Loading…";
  try {
    const res = await fetch(`/urs/${ursState.currentURS.id}/library`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ equipment_type: ursState.selectedEquipmentType }),
    }).then(r => r.json());
    ursState.requirements = res.requirements || [];
 ursToast(`${res.loaded} library requirements loaded`, "success");
 btn.textContent = `${res.loaded} requirements loaded`;
  } catch (e) {
    ursToast(`Error: ${e.message}`, "error");
    btn.disabled = false;
 btn.textContent = "Load Library Requirements";
  }
};

window.skipGeneration = async function () {
  if (!ursState.currentURS) await createURSRecord();
  if (ursState.currentURS) {
    ursState.requirements = await fetch(`/urs/${ursState.currentURS.id}/requirements`).then(r => r.json());
  }
  wizardGoTo(4);
};

// AI generation runs as a background job (services/urs_generation_job.py)
// instead of an SSE stream — the POST below returns almost instantly, and
// this polls GET /urs/<id>/generate/status until the job reaches a terminal
// state. This avoids holding an HTTP request open for the whole generation
// time, which used to exceed Render's gunicorn worker timeout.
//
// Real workflow progress (Stabilization Iteration 3): the backend reports
// progress in Gemini *batches*, not individual sections (services/
// urs_generation_job.py batches URS_GENERATION_BATCH_SIZE sections per
// call) — there is no API field naming which sections are in which batch.
// Rather than hardcode that backend batch-size constant here (fragile if
// it's ever tuned), the exact batch boundaries are reconstructed from data
// we already have: `sections` (what we requested, in request order — the
// backend batches strictly in that same order) and `generation_progress_
// total` (the batch count, known from the first status poll). Since
// batching is fixed-size contiguous chunking, batchSize =
// ceil(sections.length / total) reproduces the identical partition the
// backend used. This is what makes the ✓-per-completed-batch checklist
// below accurate rather than a guess.
//
// Every render of the progress panel is driven by one state object passed
// to renderGenerationPanel() — replacing the old design where a countdown
// timer and a requirement counter were two independently-updated DOM nodes
// that a not-quite-terminal poll (a client-side timeout racing a server
// response that had *already* arrived) could leave visibly contradicting
// each other ("59 requirements generated" next to "taking longer than
// expected"). One state object rendered in one place cannot go stale in
// only half of itself.
const URS_GENERATION_POLL_INTERVAL_MS = 1500;
const URS_GENERATION_POLL_TIMEOUT_MS = 5 * 60 * 1000;

function ursSleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function ursChunk(arr, size) {
  const out = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + Math.max(1, size)));
  return out.length ? out : [[]];
}

function ursFormatETA(ms) {
  if (!isFinite(ms) || ms <= 0) return "";
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60), s = totalSec % 60;
  return m > 0 ? `~${m}m ${s}s remaining` : `~${s}s remaining`;
}

/**
 * Single source of truth for the generation progress panel. Every call
 * fully re-renders from the state passed in — there is no other code path
 * that mutates this panel's DOM, so it can never show a stale fragment next
 * to a fresh one.
 *   phase: "starting" | "running" | "completed" | "failed" | "stalled"
 */
function renderGenerationPanel(container, { sections, batches, current, total, resultCount, phase, message, startedAt }) {
  const itemsHtml = batches.map((batchSections, i) => {
    let state;
    if (phase === "completed") state = "done";
    else if (phase === "failed" || phase === "stalled") state = i < current ? "done" : "pending";
    else state = i < current ? "done" : (i === current ? "active" : "pending");

    const icon = state === "done" ? "<span class='icon' data-lucide='check'></span>"
      : state === "active" ? "<div class='urs-gen-spinner-sm'></div>"
      : "<span class='icon' data-lucide='circle'></span>";
    const label = batchSections.join(", ") || "Additional requirements";
    const text = state === "active" ? `Generating ${label}…` : label;
    return `<div class="urs-gen-item ${state}"><div class="urs-gen-item-icon">${icon}</div><div>${escHtml(text)}</div></div>`;
  }).join("");

  const pct = total ? Math.min(100, Math.round((current / total) * 100)) : 0;
  let statusLine = "", statusClass = "";
  if (phase === "starting")      { statusLine = "Starting generation…"; }
  else if (phase === "running")  { statusLine = `Generating requirements… (batch ${current}/${total})`; }
  else if (phase === "completed"){ statusLine = message || `${resultCount} requirement${resultCount === 1 ? "" : "s"} generated`; statusClass = "success"; }
  else if (phase === "failed")   { statusLine = message || "Generation finished, but produced no requirements."; statusClass = "failed"; }
  else if (phase === "stalled")  { statusLine = "Generation is taking longer than expected."; statusClass = "stalled"; }

  const eta = (phase === "running" && current > 0 && startedAt)
    ? ursFormatETA((Date.now() - startedAt) / current * (total - current))
    : "";

  container.innerHTML = `
    <div class="urs-gen-status-line ${statusClass}">
      ${phase === "running" || phase === "starting" ? "<div class='urs-gen-spinner-sm'></div>" : ""}
      ${escHtml(statusLine)}
    </div>
    <div class="urs-gen-checklist">${itemsHtml}</div>
    <div class="urs-gen-progress-bar-track"><div class="urs-gen-progress-bar-fill" style="width:${pct}%"></div></div>
    <div class="urs-gen-footer">
      <span class="urs-gen-eta">${resultCount} requirement${resultCount === 1 ? "" : "s"} generated so far</span>
      ${eta ? `<span class="urs-gen-eta">Estimated time remaining: ${eta}</span>` : ""}
    </div>`;
}

window.runAIGeneration = async function () {
  if (!ursState.currentURS) await createURSRecord();
  if (!ursState.currentURS) return;

  const sections = [...document.querySelectorAll('input[name="section"]:checked')].map(cb => cb.value);
  if (!sections.length) { ursToast("Select at least one section", "error"); return; }

  const progress = document.getElementById("urs-gen-progress");
  const genBtn = document.getElementById("generate-btn");
  const ursId = ursState.currentURS.id;

  progress.classList.add("visible");
  genBtn.disabled = true;
  const startedAt = Date.now();
  let batches = [sections]; // best-effort placeholder until the first poll reveals the real batch count
  renderGenerationPanel(progress, { sections, batches, current: 0, total: 1, resultCount: 0, phase: "starting", startedAt });

  let job = null;
  try {
    const startResp = await fetch(`/urs/${ursId}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sections, ...ursState.wizardData }),
    });
    if (!startResp.ok) throw new Error(`Server returned HTTP ${startResp.status}`);

    const deadline = Date.now() + URS_GENERATION_POLL_TIMEOUT_MS;
    let batchesResolved = false;
    while (Date.now() < deadline) {
      const statusResp = await fetch(`/urs/${ursId}/generate/status`);
      if (!statusResp.ok) throw new Error(`Status check failed (HTTP ${statusResp.status})`);
      job = await statusResp.json();

      const total = job.generation_progress_total || 1;
      const current = job.generation_progress_current || 0;
      if (!batchesResolved && total > 0) {
        batches = ursChunk(sections, Math.ceil(sections.length / total));
        batchesResolved = true;
      }
      const isTerminal = job.generation_status === "completed" || job.generation_status === "failed";
      renderGenerationPanel(progress, {
        sections, batches, current, total,
        resultCount: job.generation_result_count || 0,
        phase: isTerminal ? job.generation_status : "running",
        message: job.generation_message, startedAt,
      });
      if (isTerminal) break;
      await ursSleep(URS_GENERATION_POLL_INTERVAL_MS);
    }

    ursState.requirements = await fetch(`/urs/${ursId}/requirements`).then(r => r.json());

    const reqCount = (job && job.generation_result_count) || 0;
    // generation_message is a human-readable per-section summary built from
    // which sections actually came back (e.g. "2 of 3 sections generated
    // successfully (11 requirements). 1 section failed and can be retried:
    // Safety Requirements.") — prefer it over the raw generation_error.
    const jobMessage = job && job.generation_message;
    const jobError = job && job.generation_error;
    const hadPartialFailure = !!jobError && reqCount > 0;
    const total = (job && job.generation_progress_total) || batches.length;
    const current = (job && job.generation_progress_current) || 0;

    if (!job || (job.generation_status !== "completed" && job.generation_status !== "failed")) {
      // The 5-minute client-side poll window elapsed with the job still
      // "running" server-side — it has NOT failed, it's still in progress
      // in the background. Distinct wording and a distinct "stalled" visual
      // state from an actual failure, and a Retry that re-polls rather than
      // silently leaving a contradictory message on screen.
      renderGenerationPanel(progress, { sections, batches, current, total, resultCount: reqCount, phase: "stalled", startedAt });
      ursNotify({
        type: "warning", title: "Still generating",
        message: "This is taking longer than expected but is still running in the background. Reopen this URS in a moment to check on it, or retry.",
        category: "Generation", retry: () => runAIGeneration(),
      });
      genBtn.disabled = false;
    } else if (job.generation_status === "failed" || reqCount === 0) {
      renderGenerationPanel(progress, { sections, batches, current, total, resultCount: reqCount, phase: "failed", message: jobMessage, startedAt });
      ursNotify({
        type: "error", title: "Generation produced no requirements",
        message: jobMessage || "AI returned no usable requirements. Try again, or add requirements manually / from the library.",
        detail: jobError || "", category: "Generation", retry: () => runAIGeneration(),
      });
      genBtn.disabled = false;
    } else {
      renderGenerationPanel(progress, { sections, batches, current, total, resultCount: reqCount, phase: "completed", message: jobMessage, startedAt });
      if (hadPartialFailure) {
        ursNotify({
          type: "warning", title: "Generation partially completed", message: jobMessage,
          detail: jobError, category: "Generation", retry: () => runAIGeneration(),
        });
        genBtn.disabled = false;
      } else {
        ursNotify({ type: "success", title: "Generation complete", message: jobMessage || `${reqCount} requirements generated` });
      }
      // Automatic transition to the Requirements review step once generation
      // finishes — the user shouldn't have to manually navigate forward.
      setTimeout(() => wizardGoTo(4), hadPartialFailure ? 1800 : 900);
    }
  } catch (e) {
    renderGenerationPanel(progress, { sections, batches, current: 0, total: batches.length, resultCount: 0, phase: "failed", message: e.message, startedAt });
    ursNotify({
      type: "error", title: "Generation failed to start", message: e.message,
      category: "Generation", retry: () => runAIGeneration(),
    });
    genBtn.disabled = false;
  }
};

async function createURSRecord() {
  try {
    const urs = await fetch("/urs/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ursState.wizardData),
    }).then(r => r.json());
    ursState.currentURS = urs;
  } catch (e) {
    ursToast(`Failed to create URS: ${e.message}`, "error");
  }
}

/* ── Step 4: Requirements Editor ────────────────────────────────────────────── */
function renderStep4(body) {
  const reqs = ursState.requirements;
  body.innerHTML = `
  <div class="urs-section-header"><div class="section-icon"><span class=\'icon\' data-lucide=\'clipboard-list\'></span></div>Review & Edit Requirements</div>

  <div class="urs-req-toolbar">
    <div class="urs-req-toolbar-left">
      <span class="urs-req-count">${reqs.length} Requirements</span>
      <select class="urs-req-filter" id="req-filter-section" onchange="filterRequirementsTable()">
        <option value="">All Sections</option>
        ${[...new Set(reqs.map(r => r.section))].map(s => `<option>${s}</option>`).join("")}
      </select>
      <select class="urs-req-filter" id="req-filter-priority" onchange="filterRequirementsTable()">
        <option value="">All Priorities</option>
        <option>Critical</option><option>High</option><option>Medium</option><option>Low</option>
      </select>
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn-urs-outline" onclick="addNewRow()"><span class=\'icon\' data-lucide=\'plus\'></span> Add Row</button>
      <button class="btn-urs-outline" onclick="saveAllRequirements()"><span class=\'icon\' data-lucide=\'save\'></span> Save</button>
    </div>
  </div>

  <div class="urs-table-wrap">
    <table class="urs-table" id="req-table">
      <thead>
        <tr>
          <th style="width:90px">Req ID</th>
          <th style="width:130px">Section</th>
          <th>Requirement</th>
          <th style="width:90px">Priority</th>
          <th style="width:100px">GMP Criticality</th>
          <th style="width:120px">Verification Method</th>
          <th style="width:150px">Acceptance Criteria</th>
          <th style="width:60px">Actions</th>
        </tr>
      </thead>
      <tbody id="req-tbody">
        ${reqs.map((r, i) => buildReqRow(r, i)).join("")}
      </tbody>
    </table>
  </div>

  <div style="display:flex;justify-content:space-between;margin-top:20px">
    <button class="btn-urs-secondary" style="background:rgba(61,47,33,.06);color:var(--navy);border-color:var(--border)" onclick="wizardBack()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
    <div style="display:flex;gap:10px">
      <button class="btn-urs-outline" onclick="saveAllRequirements()"><span class=\'icon\' data-lucide=\'save\'></span> Save Requirements</button>
      <button class="btn-urs-primary" onclick="wizardNext()">Next: Submit URS <span class=\'icon\' data-lucide=\'arrow-right\'></span></button>
    </div>
  </div>`;
}

function buildReqRow(req, idx) {
  const priorityBadge = `<span class="priority-badge ${req.priority || 'Medium'}">${req.priority || 'Medium'}</span>`;
  const gmpBadge = `<span class="gmp-badge ${(req.gmp_criticality || '').replace(/-/g,'-')}">${req.gmp_criticality || 'GMP'}</span>`;

  return `<tr data-idx="${idx}" data-id="${req.id || ''}">
    <td class="req-id"><span contenteditable="true" class="editable" data-field="req_id">${escHtml(req.req_id || '')}</span></td>
    <td class="req-section"><select class="urs-req-filter" style="width:100%;font-size:12px" data-field="section" onchange="markRowDirty(this)">
      ${REQUIREMENT_SECTIONS.map(s => `<option ${s===req.section?'selected':''}>${s}</option>`).join("")}
    </select></td>
    <td class="req-text"><span contenteditable="true" class="editable" data-field="requirement">${escHtml(req.requirement || '')}</span></td>
    <td><select class="urs-req-filter" style="width:80px;font-size:12px" data-field="priority" onchange="markRowDirty(this)">
      <option ${req.priority==='Critical'?'selected':''}>Critical</option>
      <option ${req.priority==='High'?'selected':''}>High</option>
      <option ${req.priority==='Medium'?'selected':''}>Medium</option>
      <option ${req.priority==='Low'?'selected':''}>Low</option>
    </select></td>
    <td><select class="urs-req-filter" style="width:95px;font-size:12px" data-field="gmp_criticality" onchange="markRowDirty(this)">
      <option ${req.gmp_criticality==='GMP-Critical'?'selected':''}>GMP-Critical</option>
      <option ${req.gmp_criticality==='GMP'?'selected':''}>GMP</option>
      <option ${req.gmp_criticality==='Non-GMP'?'selected':''}>Non-GMP</option>
    </select></td>
    <td><span contenteditable="true" class="editable" data-field="verification_method" style="font-size:12px">${escHtml(req.verification_method || '')}</span></td>
    <td><span contenteditable="true" class="editable" data-field="acceptance_criteria" style="font-size:12px">${escHtml(req.acceptance_criteria || '')}</span></td>
    <td><div class="req-row-actions">
 <button class="req-action-btn delete"title="Delete"onclick="deleteRow(this)"></button>
    </div></td>
  </tr>`;
}

window.markRowDirty = function (el) { el.closest("tr").dataset.dirty = "1"; };

window.filterRequirementsTable = function () {
  const section = document.getElementById("req-filter-section")?.value || "";
  const priority = document.getElementById("req-filter-priority")?.value || "";
  document.querySelectorAll("#req-tbody tr").forEach(row => {
    const rowSection = row.querySelector('[data-field="section"]')?.value || "";
    const rowPriority = row.querySelector('[data-field="priority"]')?.value || "";
    const show = (!section || rowSection === section) && (!priority || rowPriority === priority);
    row.style.display = show ? "" : "none";
  });
};

window.addNewRow = function () {
  const tbody = document.getElementById("req-tbody");
  if (!tbody) return;
  const newReq = {
    req_id: "NEW-001", section: "General Requirements", requirement: "The system shall…",
    priority: "Medium", gmp_criticality: "GMP", verification_method: "Functional Test",
    acceptance_criteria: "", id: "", rationale: "", regulatory_ref: "",
  };
  const idx = tbody.querySelectorAll("tr").length;
  tbody.insertAdjacentHTML("beforeend", buildReqRow(newReq, idx));
};

window.deleteRow = function (btn) {
  if (confirm("Delete this requirement?")) {
    btn.closest("tr").remove();
  }
};

function collectTableRequirements() {
  const rows = document.querySelectorAll("#req-tbody tr");
  const reqs = [];
  rows.forEach((row, i) => {
    const get = (field) => {
      const el = row.querySelector(`[data-field="${field}"]`);
      if (!el) return "";
      return el.tagName === "SELECT" ? el.value : el.textContent.trim();
    };
    reqs.push({
      id: row.dataset.id || "",
      req_id: get("req_id"),
      section: get("section"),
      requirement: get("requirement"),
      priority: get("priority"),
      gmp_criticality: get("gmp_criticality"),
      verification_method: get("verification_method"),
      acceptance_criteria: get("acceptance_criteria"),
      rationale: "", regulatory_ref: "", status: "draft", source: "ai",
    });
  });
  return reqs;
}

window.saveAllRequirements = async function () {
  if (!ursState.currentURS) { ursToast("No URS created yet", "error"); return; }
  const reqs = collectTableRequirements();
  try {
    const saved = await fetch(`/urs/${ursState.currentURS.id}/requirements`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reqs),
    }).then(r => r.json());
    ursState.requirements = saved;
 ursToast(`${saved.length} requirements saved`, "success");
  } catch (e) {
    ursToast(`Save error: ${e.message}`, "error");
  }
};

/* ── Step 5: Submit ─────────────────────────────────────────────────────────── */
function renderStep5(body) {
  const urs = ursState.currentURS || {};
  const reqCount = ursState.requirements.length;
  body.innerHTML = `
  <div class="urs-section-header"><div class="section-icon"><span class=\'icon\' data-lucide=\'check-circle-2\'></span></div>URS Ready for Submission</div>

  <div style="background:linear-gradient(135deg,#E8F2EA,#E8F2EA);border:1px solid #E8F2EA;border-radius:12px;padding:24px;margin-bottom:24px;text-align:center">
    <div style="font-size:48px;margin-bottom:12px"><span class=\'icon\' data-lucide=\'party-popper\'></span></div>
    <div style="font-size:20px;font-weight:700;color:#5F8A61;margin-bottom:8px">URS Successfully Created!</div>
    <div style="font-size:14px;color:#5F8A61">${reqCount} requirements captured for <strong>${escHtml(urs.equipment_name || ursState.wizardData.equipment_name || "")}</strong></div>
  </div>

  <div class="urs-info-grid">
    <div class="urs-info-card">
      <div class="urs-info-card-title">Document Details <span style="font-weight:400;text-transform:none;letter-spacing:0">(system-assigned)</span></div>
      <div class="urs-info-row"><label>URS Number</label><span>${escHtml(urs.urs_number || "—")}</span></div>
      <div class="urs-info-row"><label>Document Number</label><span>${escHtml(urs.doc_number || "—")}</span></div>
      <div class="urs-info-row"><label>Version / Revision</label><span>${escHtml(urs.version || "1.0")} / ${escHtml(urs.revision || "A")}</span></div>
      <div class="urs-info-row"><label>Prepared By</label><span>${escHtml(urs.prepared_by || "—")}</span></div>
      <div class="urs-info-row"><label>Title</label><span>${escHtml(urs.title || ursState.wizardData.title || "—")}</span></div>
      <div class="urs-info-row"><label>Status</label><span>${formatStatus(urs.status || "draft")}</span></div>
      <div class="urs-info-row"><label>Requirements</label><span>${reqCount}</span></div>
    </div>
    <div class="urs-info-card">
      <div class="urs-info-card-title">Next Steps</div>
      <div style="display:flex;flex-direction:column;gap:10px">
        <div style="display:flex;align-items:center;gap:10px;font-size:13px">
          <span style="color:#5F8A61;font-weight:700"><span class=\'icon\' data-lucide=\'check\'></span></span> URS draft created
        </div>
        <div style="display:flex;align-items:center;gap:10px;font-size:13px">
          <span style="color:var(--blue);font-weight:700"><span class=\'icon\' data-lucide=\'arrow-right\'></span></span> Submit for review
        </div>
        <div style="display:flex;align-items:center;gap:10px;font-size:13px">
          <span style="color:var(--text-muted)">○</span> QA / SME review
        </div>
        <div style="display:flex;align-items:center;gap:10px;font-size:13px">
          <span style="color:var(--text-muted)">○</span> Approval
        </div>
        <div style="display:flex;align-items:center;gap:10px;font-size:13px">
          <span style="color:var(--text-muted)">○</span> Baseline for IQ/OQ/PQ
        </div>
      </div>
    </div>
  </div>

  <div style="display:flex;gap:12px;justify-content:center;margin-top:8px;flex-wrap:wrap">
    ${urs.id ? `
    <button class="btn-urs-primary" onclick="openURS(${urs.id})"><span class=\'icon\' data-lucide=\'folder-open\'></span> Open URS</button>
    <button class="btn-urs-outline urs-export-btn" data-export-state="idle" onclick="exportURSDocx(${urs.id}, '${escHtml(urs.urs_number || 'URS')}', this)">
      <div class="urs-btn-spinner"></div><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span>
      <span class="urs-btn-label-idle">Export DOCX</span><span class="urs-btn-label-busy">Preparing…</span><span class="urs-btn-label-done">Downloaded</span>
    </button>
    <button class="btn-urs-outline" onclick="submitForReview(${urs.id})"><span class=\'icon\' data-lucide=\'mail\'></span> Submit for Review</button>
    ` : ""}
    <button class="btn-urs-outline" onclick="startNewURS()"><span class=\'icon\' data-lucide=\'plus\'></span> Create Another URS</button>
    <button class="btn-urs-outline" onclick="loadURSList()"><span class=\'icon\' data-lucide=\'clipboard-list\'></span> View All URS</button>
  </div>`;
}

/* ── Wizard Navigation ──────────────────────────────────────────────────────── */
window.wizardNext = async function () {
  const step = ursState.wizardStep;
  if (step === 1) {
    if (!ursState.selectedEquipmentType) { ursToast("Select an equipment type", "error"); return; }
    wizardGoTo(2);
  } else if (step === 2) {
    collectStep2Data();
    if (!ursState.wizardData.title?.trim()) { ursToast("URS title is required", "error"); return; }
    if (!ursState.currentURS) await createURSRecord();
    else await fetch(`/urs/${ursState.currentURS.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(ursState.wizardData) });
    wizardGoTo(3);
  } else if (step === 3) {
    wizardGoTo(4);
  } else if (step === 4) {
    await saveAllRequirements();
    wizardGoTo(5);
  }
};

window.wizardBack = function () {
  if (ursState.wizardStep > 1) wizardGoTo(ursState.wizardStep - 1);
};

function wizardGoTo(step) {
  ursState.wizardStep = step;
  renderWizardStep(step);
}

/* ─────────────────────────────────────────────────────────────────────────────
   DETAIL VIEW
────────────────────────────────────────────────────────────────────────────── */
window.openURS = async function (id) {
  showView("view-urs-detail");
  const titleEl = document.getElementById("urs-detail-title");
  if (titleEl) titleEl.textContent = "Loading…";

  try {
    const [urs, reqs] = await Promise.all([
      fetch(`/urs/${id}`).then(r => r.json()),
      fetch(`/urs/${id}/requirements`).then(r => r.json()),
    ]);
    ursState.currentURS = urs;
    ursState.requirements = reqs;
    renderDetailView(urs, reqs);
  } catch (e) {
    ursToast(`Error: ${e.message}`, "error");
  }
};

function renderDetailView(urs, reqs) {
  if (document.getElementById("urs-detail-title"))
    document.getElementById("urs-detail-title").textContent = urs.title || "URS";

  // Status badge
  const badge = document.getElementById("urs-detail-status");
  if (badge) {
    badge.textContent = formatStatus(urs.status);
    badge.className = `urs-tag urs-tag-status ${urs.status}`;
  }

  switchDetailTab("overview", urs, reqs);
}

window.switchDetailTab = function (tab, urs, reqs) {
  urs = urs || ursState.currentURS;
  reqs = reqs || ursState.requirements;
  if (!urs) return;
  ursState.activeDetailTab = tab;

  document.querySelectorAll(".urs-detail-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.tab === tab);
  });
  document.querySelectorAll(".urs-detail-panel").forEach(p => {
    p.classList.toggle("active", p.dataset.tab === tab);
  });

  const panel = document.querySelector(`.urs-detail-panel[data-tab="${tab}"]`);
  if (!panel) return;

  if (tab === "overview") renderOverviewPanel(panel, urs, reqs);
  else if (tab === "requirements") renderRequirementsPanel(panel, urs, reqs);
  else if (tab === "review") renderReviewPanel(panel, urs);
  else if (tab === "approval") renderApprovalPanel(panel, urs);
  else if (tab === "versions") renderVersionsPanel(panel, urs);
  else if (tab === "traceability") renderTraceabilityPanel(panel, urs);
};

/* ── Overview Tab ───────────────────────────────────────────────────────────── */
function renderOverviewPanel(panel, urs, reqs) {
  const critical = reqs.filter(r => r.priority === "Critical").length;
  const gmpCritical = reqs.filter(r => r.gmp_criticality === "GMP-Critical").length;
  const sectionCounts = {};
  reqs.forEach(r => { sectionCounts[r.section] = (sectionCounts[r.section] || 0) + 1; });

  panel.innerHTML = `
  <div class="urs-info-grid">
    <div class="urs-info-card">
      <div class="urs-info-card-title">Document Information</div>
      ${infoRow("URS Number", urs.urs_number)}
      ${infoRow("Document Number", urs.doc_number)}
      ${infoRow("Version", urs.version || "1.0")}
      ${infoRow("Revision", urs.revision)}
      ${infoRow("Status", formatStatus(urs.status))}
      ${infoRow("Category", urs.category)}
      ${infoRow("Equipment Type", urs.equipment_type)}
      ${infoRow("Validation Type", urs.validation_type)}
    </div>
    <div class="urs-info-card">
      <div class="urs-info-card-title">Equipment Details</div>
      ${infoRow("Equipment Name", urs.equipment_name)}
      ${infoRow("Equipment ID", urs.equipment_id)}
      ${infoRow("Manufacturer", urs.manufacturer)}
      ${infoRow("Model", urs.model)}
      ${infoRow("Capacity", urs.capacity)}
      ${infoRow("Department", urs.department)}
      ${infoRow("Site / Location", [urs.site, urs.location].filter(Boolean).join(", "))}
    </div>
    <div class="urs-info-card">
      <div class="urs-info-card-title">Responsibility</div>
      ${infoRow("Prepared By", urs.prepared_by)}
      ${infoRow("Reviewed By", urs.reviewed_by)}
      ${infoRow("Approved By", urs.approved_by)}
      ${infoRow("Effective Date", urs.effective_date)}
      ${infoRow("Created", formatDate(urs.created_at))}
      ${infoRow("Updated", formatDate(urs.updated_at))}
    </div>
    <div class="urs-info-card">
      <div class="urs-info-card-title">Requirements Summary</div>
      ${infoRow("Total Requirements", reqs.length)}
      ${infoRow("Critical Priority", critical)}
      ${infoRow("GMP-Critical", gmpCritical)}
      ${infoRow("Sections", Object.keys(sectionCounts).length)}
      ${urs.compliance_score ? infoRow("Compliance Score", `${urs.compliance_score}%`) : ""}
      ${urs.completeness_score ? infoRow("Completeness Score", `${urs.completeness_score}%`) : ""}
    </div>
  </div>
  ${urs.purpose ? `<div class="urs-info-card" style="margin-bottom:16px">
    <div class="urs-info-card-title">Purpose</div><p style="font-size:14px;line-height:1.6">${escHtml(urs.purpose)}</p>
  </div>` : ""}
  <div style="display:flex;gap:10px;margin-top:4px;flex-wrap:wrap;align-items:center">
    <button class="btn-urs-primary urs-export-btn" data-export-state="idle" onclick="exportURSDocx(${urs.id}, '${escHtml(urs.urs_number||'URS')}', this)">
      <div class="urs-btn-spinner"></div><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span>
      <span class="urs-btn-label-idle">Export DOCX</span>
      <span class="urs-btn-label-busy">Preparing…</span>
      <span class="urs-btn-label-done">Downloaded</span>
    </button>
    ${ursValidActionsFor(urs.status).includes("Submitted for Review")
      ? `<button class="btn-urs-outline" onclick="submitForReview(${urs.id})"><span class=\'icon\' data-lucide=\'mail\'></span> Submit for Review</button>`
      : `<span class="urs-lifecycle-hint" style="margin:0">Submit for Review not available from ${formatStatus(urs.status)}</span>`}
    <button class="btn-urs-outline" onclick="switchDetailTab('review')"><span class=\'icon\' data-lucide=\'bot\'></span> AI Review</button>
    <button class="btn-urs-outline" onclick="createVersionSnapshot(${urs.id})"><span class=\'icon\' data-lucide=\'camera\'></span> Snapshot Version</button>
  </div>`;
}

/* ── Requirements Tab ───────────────────────────────────────────────────────── */
function renderRequirementsPanel(panel, urs, reqs) {
  panel.innerHTML = `
  <div class="urs-req-toolbar">
    <div class="urs-req-toolbar-left">
      <span class="urs-req-count">${reqs.length} Requirements</span>
      <select class="urs-req-filter" id="detail-filter-section" onchange="filterDetailTable()">
        <option value="">All Sections</option>
        ${[...new Set(reqs.map(r => r.section))].map(s => `<option>${s}</option>`).join("")}
      </select>
      <select class="urs-req-filter" id="detail-filter-priority" onchange="filterDetailTable()">
        <option value="">All Priorities</option>
        <option>Critical</option><option>High</option><option>Medium</option><option>Low</option>
      </select>
      <select class="urs-req-filter" id="detail-filter-gmp" onchange="filterDetailTable()">
        <option value="">All GMP</option>
        <option>GMP-Critical</option><option>GMP</option><option>Non-GMP</option>
      </select>
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn-urs-outline" onclick="addDetailRow()"><span class=\'icon\' data-lucide=\'plus\'></span> Add</button>
      <button class="btn-urs-primary" onclick="saveDetailRequirements()"><span class=\'icon\' data-lucide=\'save\'></span> Save</button>
    </div>
  </div>
  <div class="urs-table-wrap">
    <table class="urs-table" id="detail-req-table">
      <thead>
        <tr>
          <th style="width:90px">Req ID</th>
          <th style="width:130px">Section</th>
          <th>Requirement</th>
          <th style="width:200px">Rationale</th>
          <th style="width:90px">Priority</th>
          <th style="width:100px">GMP Criticality</th>
          <th style="width:130px">Regulatory Ref.</th>
          <th style="width:120px">Verification</th>
          <th style="width:140px">Acceptance Criteria</th>
          <th style="width:50px"></th>
        </tr>
      </thead>
      <tbody id="detail-req-tbody">
        ${reqs.map((r, i) => buildDetailRow(r, i)).join("")}
      </tbody>
    </table>
  </div>`;
}

function buildDetailRow(req, idx) {
  return `<tr data-idx="${idx}" data-id="${req.id || ''}">
    <td class="req-id"><span contenteditable="true" data-field="req_id">${escHtml(req.req_id || '')}</span></td>
    <td class="req-section"><select class="urs-req-filter" style="width:100%;font-size:12px" data-field="section">
      ${REQUIREMENT_SECTIONS.map(s => `<option ${s===req.section?'selected':''}>${s}</option>`).join("")}
    </select></td>
    <td class="req-text"><span contenteditable="true" data-field="requirement">${escHtml(req.requirement || '')}</span></td>
    <td><span contenteditable="true" data-field="rationale" style="font-size:12px">${escHtml(req.rationale || '')}</span></td>
    <td><select class="urs-req-filter" style="width:80px;font-size:12px" data-field="priority">
      <option ${req.priority==='Critical'?'selected':''}>Critical</option>
      <option ${req.priority==='High'?'selected':''}>High</option>
      <option ${req.priority==='Medium'?'selected':''}>Medium</option>
      <option ${req.priority==='Low'?'selected':''}>Low</option>
    </select></td>
    <td><select class="urs-req-filter" style="width:95px;font-size:12px" data-field="gmp_criticality">
      <option ${req.gmp_criticality==='GMP-Critical'?'selected':''}>GMP-Critical</option>
      <option ${req.gmp_criticality==='GMP'?'selected':''}>GMP</option>
      <option ${req.gmp_criticality==='Non-GMP'?'selected':''}>Non-GMP</option>
    </select></td>
    <td><span contenteditable="true" data-field="regulatory_ref" style="font-size:11px">${escHtml(req.regulatory_ref || '')}</span></td>
    <td><span contenteditable="true" data-field="verification_method" style="font-size:12px">${escHtml(req.verification_method || '')}</span></td>
    <td><span contenteditable="true" data-field="acceptance_criteria" style="font-size:12px">${escHtml(req.acceptance_criteria || '')}</span></td>
    <td><div class="req-row-actions">
 <button class="req-action-btn delete"title="Delete"onclick="deleteDetailRow(this)"></button>
    </div></td>
  </tr>`;
}

window.deleteDetailRow = function (btn) {
  if (confirm("Delete this requirement?")) btn.closest("tr").remove();
};

window.addDetailRow = function () {
  const tbody = document.getElementById("detail-req-tbody");
  if (!tbody) return;
  const idx = tbody.querySelectorAll("tr").length;
  const newReq = { req_id: "", section: "General Requirements", requirement: "The system shall…",
    rationale: "", priority: "Medium", gmp_criticality: "GMP", regulatory_ref: "",
    verification_method: "Functional Test", acceptance_criteria: "", id: "" };
  tbody.insertAdjacentHTML("beforeend", buildDetailRow(newReq, idx));
};

window.filterDetailTable = function () {
  const section = document.getElementById("detail-filter-section")?.value || "";
  const priority = document.getElementById("detail-filter-priority")?.value || "";
  const gmp = document.getElementById("detail-filter-gmp")?.value || "";
  document.querySelectorAll("#detail-req-tbody tr").forEach(row => {
    const s = row.querySelector('[data-field="section"]')?.value || "";
    const p = row.querySelector('[data-field="priority"]')?.value || "";
    const g = row.querySelector('[data-field="gmp_criticality"]')?.value || "";
    const show = (!section || s === section) && (!priority || p === priority) && (!gmp || g === gmp);
    row.style.display = show ? "" : "none";
  });
};

window.saveDetailRequirements = async function () {
  const uid = ursState.currentURS?.id;
  if (!uid) return;
  const rows = document.querySelectorAll("#detail-req-tbody tr");
  const reqs = [];
  rows.forEach((row, i) => {
    const get = (field) => {
      const el = row.querySelector(`[data-field="${field}"]`);
      if (!el) return "";
      return el.tagName === "SELECT" ? el.value : el.textContent.trim();
    };
    reqs.push({
      req_id: get("req_id"), section: get("section"), requirement: get("requirement"),
      rationale: get("rationale"), priority: get("priority"), gmp_criticality: get("gmp_criticality"),
      regulatory_ref: get("regulatory_ref"), verification_method: get("verification_method"),
      acceptance_criteria: get("acceptance_criteria"), source: "manual", status: "draft",
    });
  });
  try {
    const saved = await fetch(`/urs/${uid}/requirements`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(reqs),
    }).then(r => r.json());
    ursState.requirements = saved;
 ursToast(`${saved.length} requirements saved`, "success");
  } catch (e) {
    ursToast(`Error: ${e.message}`, "error");
  }
};

/* ── Review Tab ─────────────────────────────────────────────────────────────── */
function renderReviewPanel(panel, urs) {
  const review = urs.ai_review_data || {};
  const hasReview = review.compliance_score > 0;

  if (!hasReview) {
    panel.innerHTML = `
    <div class="urs-ai-panel">
      <div class="urs-ai-panel-header">
        <div class="urs-ai-icon"><span class=\'icon\' data-lucide=\'bot\'></span></div>
        <div>
          <div class="urs-ai-panel-title">AI Review Engine</div>
          <div class="urs-ai-panel-sub">Gemini will analyze your URS for completeness, regulatory compliance, and GMP readiness.</div>
        </div>
      </div>
      <button class="btn-urs-primary" id="run-review-btn" onclick="runAIReview(${urs.id})">▶ Run AI Review</button>
      <div class="urs-gen-progress" id="review-progress" style="margin-top:14px">
        <div class="urs-gen-spinner"></div>
        <div class="urs-gen-text">Reviewing requirements…</div>
      </div>
    </div>`;
    return;
  }

  const compScore = review.compliance_score || 0;
  const compClass = compScore >= 90 ? "excellent" : compScore >= 75 ? "good" : compScore >= 60 ? "fair" : "poor";
  const cmpScore = review.completeness_score || 0;
  const cmpClass = cmpScore >= 90 ? "excellent" : cmpScore >= 75 ? "good" : cmpScore >= 60 ? "fair" : "poor";

  panel.innerHTML = `
  <div class="urs-review-panel">
    <div class="urs-review-scores">
      <div class="urs-score-block">
        <div class="urs-score-circle ${compClass}">${compScore}%</div>
        <div class="urs-score-label">Compliance Score</div>
      </div>
      <div class="urs-score-block">
        <div class="urs-score-circle ${cmpClass}">${cmpScore}%</div>
        <div class="urs-score-label">Completeness Score</div>
      </div>
    </div>
    <div class="urs-review-body">
      ${review.overall_assessment ? `<div class="urs-review-section">
        <div class="urs-review-section-title">Overall Assessment</div>
        <p style="font-size:14px;line-height:1.6">${escHtml(review.overall_assessment)}</p>
      </div>` : ""}
      ${review.recommendation ? `<div class="urs-review-section">
        <span class="urs-recommendation ${review.recommendation.includes('Approved')?'approved':review.recommendation.includes('Major')?'major':'revision'}">
          ${review.recommendation}
        </span>
      </div>` : ""}
      ${renderReviewList("Strengths", review.strengths || [], "strength")}
      ${renderReviewList("Missing Requirements", review.missing_requirements || [], "missing")}
      ${renderReviewList("Improvement Suggestions", review.improvements || [], "")}
      ${renderReviewList("Regulatory Gaps", review.regulatory_gaps || [], "missing")}
      ${renderReviewList("Risk Flags", review.risk_flags || [], "missing")}
      ${review.data_integrity_assessment ? `<div class="urs-review-section">
        <div class="urs-review-section-title">Data Integrity Assessment</div>
        <p style="font-size:13px;line-height:1.6">${escHtml(review.data_integrity_assessment)}</p>
      </div>` : ""}
      ${review.csv_readiness ? `<div class="urs-review-section">
        <div class="urs-review-section-title">CSV Readiness</div>
        <p style="font-size:13px;line-height:1.6">${escHtml(review.csv_readiness)}</p>
      </div>` : ""}
    </div>
  </div>
  <div style="margin-top:16px">
    <button class="btn-urs-outline" onclick="runAIReview(${urs.id})"><span class=\'icon\' data-lucide=\'refresh-cw\'></span> Re-run Review</button>
  </div>`;
}

function renderReviewList(title, items, cls) {
  if (!items.length) return "";
  return `<div class="urs-review-section">
    <div class="urs-review-section-title">${title}</div>
    <ul class="urs-review-list ${cls}">
      ${items.map(i => `<li>${escHtml(i)}</li>`).join("")}
    </ul>
  </div>`;
}

window.runAIReview = async function (uid) {
  const progress = document.getElementById("review-progress");
  const btn = document.getElementById("run-review-btn");
  if (progress) progress.classList.add("visible");
  if (btn) btn.disabled = true;

  try {
    const review = await fetch(`/urs/${uid}/review`, { method: "POST" }).then(r => r.json());
    ursState.currentURS = { ...ursState.currentURS, ai_review_data: review, ...review };
    renderReviewPanel(
      document.querySelector('.urs-detail-panel[data-tab="review"]'),
      ursState.currentURS
    );
 ursToast("AI Review complete", "success");
  } catch (e) {
    ursToast(`Review failed: ${e.message}`, "error");
    if (btn) btn.disabled = false;
    if (progress) progress.classList.remove("visible");
  }
};

/* ── Approval Tab ───────────────────────────────────────────────────────────── */
// Mirrors pharmagpt/services/urs_lifecycle.py's ALLOWED_TRANSITIONS and
// routes/urs.py's _ACTION_STATUS_MAP — a presentation-only duplication so
// the action dropdown only ever offers actions the backend will actually
// accept from the document's current status, instead of letting a user
// pick something and find out it's invalid from a 409 after submitting.
// The backend remains the sole source of truth and still validates
// independently (see the 409 handling in addApprovalEntry below, which
// covers the case where the status changed in another tab since this
// panel was rendered) — this only prevents the *obviously* invalid case.
const URS_LIFECYCLE_TRANSITIONS = {
  draft:            ["under_review"],
  under_review:     ["pending_approval", "approved", "draft"],
  pending_approval: ["approved", "draft"],
  approved:         ["effective", "draft"],
  effective:        ["obsolete"],
  obsolete:         [],
};
const URS_ACTION_STATUS_MAP = {
  "Submitted for Review":   "under_review",
  "Review Complete":        "under_review",
  "Submitted for Approval": "pending_approval",
  "Approved":               "approved",
  "Rejected":                "draft",
  "Make Effective":          "effective",
  "Obsolete":                 "obsolete",
};

function ursValidActionsFor(status) {
  const allowed = new Set(URS_LIFECYCLE_TRANSITIONS[status] || []);
  return Object.keys(URS_ACTION_STATUS_MAP).filter(a => allowed.has(URS_ACTION_STATUS_MAP[a]));
}

function renderApprovalPanel(panel, urs) {
  const user = window.PharmaAuth && PharmaAuth.getUser && PharmaAuth.getUser();
  const validActions = ursValidActionsFor(urs.status);
  const noActionsAvailable = validActions.length === 0;

  panel.innerHTML = `
  <div class="urs-lifecycle-current">
    <span class="urs-tag urs-tag-status ${urs.status}">${formatStatus(urs.status)}</span>
    <span>is the current document status</span>
  </div>

  <div class="urs-info-grid" style="grid-template-columns:1fr;margin-bottom:20px">
    <div class="urs-info-card">
      <div class="urs-info-card-title">Reviewed By / Approved By / QA Approval</div>
      ${infoRow("Reviewed By", urs.reviewed_by)}
      ${infoRow("Approved By", urs.approved_by)}
      ${infoRow("QA Approval", urs.approved_by ? "Approved" : "Pending")}
      ${infoRow("Effective Date", urs.effective_date)}
    </div>
  </div>

  <div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
    <div style="flex:1;min-width:280px">
      <div class="urs-section-header" style="margin-bottom:16px"><div class="section-icon"><span class=\'icon\' data-lucide=\'check-circle-2\'></span></div>Approval Trail</div>
      <div class="urs-approval-timeline" id="approval-timeline">
        <div class="urs-empty" style="padding:20px"><div class="urs-gen-spinner" style="margin:0 auto"></div></div>
      </div>
    </div>
    <div style="width:280px;flex-shrink:0">
      <div class="urs-section-header" style="margin-bottom:16px"><div class="section-icon"><span class=\'icon\' data-lucide=\'plus\'></span></div>Add Entry</div>
      ${noActionsAvailable ? `
        <div class="urs-lifecycle-hint">This document is <strong>${formatStatus(urs.status)}</strong> — no further lifecycle transitions are available from here.</div>
      ` : `
        <div class="urs-field" style="margin-bottom:12px">
          <label class="urs-label">Action</label>
          <select class="urs-select" id="approval-action" onchange="updateApprovalActionHint()">
            ${validActions.map(a => `<option>${a}</option>`).join("")}
          </select>
          <div class="urs-lifecycle-hint" id="approval-action-hint"></div>
        </div>
        <div class="urs-field" style="margin-bottom:12px">
          <label class="urs-label">Performed By</label>
          ${user ? `
            <div class="urs-identity-chip"><span class=\'icon\' data-lucide=\'user-check\'></span> <strong>${escHtml(user.display_name || user.email || "You")}</strong>${user.role ? ` (${escHtml(user.role)})` : ""}</div>
          ` : `
            <input class="urs-input" id="approval-name" placeholder="Your name" style="margin-bottom:8px">
            <input class="urs-input" id="approval-role" placeholder="e.g. QA Manager">
          `}
        </div>
        <div class="urs-field" style="margin-bottom:12px">
          <label class="urs-label">Comments</label>
          <textarea class="urs-textarea" id="approval-comments" placeholder="Optional comments…"></textarea>
        </div>
        <button class="btn-urs-primary" style="width:100%" id="approval-submit-btn" onclick="addApprovalEntry(${urs.id})">Add Entry</button>
      `}
    </div>
  </div>`;
  loadApprovalTrail(urs.id);
  if (!noActionsAvailable) updateApprovalActionHint();
}

window.updateApprovalActionHint = function () {
  const sel = document.getElementById("approval-action");
  const hint = document.getElementById("approval-action-hint");
  if (!sel || !hint) return;
  const target = URS_ACTION_STATUS_MAP[sel.value];
  hint.textContent = target ? `This will move the document status to: ${formatStatus(target)}` : "";
};

async function loadApprovalTrail(uid) {
  const timeline = document.getElementById("approval-timeline");
  if (!timeline) return;
  try {
    const resp = await fetch(`/urs/${uid}/approval`);
    if (!resp.ok) throw new Error(`Server returned HTTP ${resp.status}`);
    const entries = await resp.json();
    if (!entries.length) {
      timeline.innerHTML = `<div class="urs-empty" style="padding:20px"><p>No entries yet.</p></div>`;
      return;
    }
    timeline.innerHTML = entries.map(e => `
      <div class="urs-approval-entry">
        <div class="urs-approval-dot"></div>
        <div class="urs-approval-card">
          <div class="urs-approval-action">${escHtml(e.action)}</div>
          <div class="urs-approval-meta"><span class=\'icon\' data-lucide=\'user\'></span> ${escHtml(e.performed_by || "—")} · ${escHtml(e.role || "")} · <span class=\'icon\' data-lucide=\'calendar\'></span> ${formatDate(e.created_at)}</div>
          ${e.comments ? `<div class="urs-approval-comments">${escHtml(e.comments)}</div>` : ""}
        </div>
      </div>`).join("");
  } catch (err) {
    timeline.innerHTML = ursErrorStateHTML("Couldn't load the approval trail", err.message, `loadApprovalTrail(${uid})`);
  }
}

window.addApprovalEntry = async function (uid) {
  const action = document.getElementById("approval-action")?.value;
  const user = window.PharmaAuth && PharmaAuth.getUser && PharmaAuth.getUser();
  const name = user ? (user.display_name || user.email || "") : (document.getElementById("approval-name")?.value.trim() || "");
  const role = user ? (user.role || "") : (document.getElementById("approval-role")?.value.trim() || "");
  const comments = document.getElementById("approval-comments")?.value.trim();
  if (!name) { ursToast("Name is required", "error"); return; }

  const btn = document.getElementById("approval-submit-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Submitting…"; }

  try {
    const resp = await fetch(`/urs/${uid}/approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, performed_by: name, role, comments }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      if (resp.status === 409) {
        // Someone else (or another tab) moved the document's status since
        // this panel was rendered — reload it so the action list reflects
        // reality instead of leaving the user staring at a now-stale form.
        ursState.currentURS = await fetch(`/urs/${uid}`).then(r => r.json());
        refreshDetailStatusBadge();
        renderApprovalPanel(document.querySelector('.urs-detail-panel[data-tab="approval"]'), ursState.currentURS);
        ursNotify({
          type: "warning", title: "Status changed since this page loaded",
          message: body.error || "This action is no longer valid for the document's current status. The form has been refreshed.",
          category: "Validation",
        });
        return;
      }
      throw new Error(body.error || `Server returned HTTP ${resp.status}`);
    }
    ursState.currentURS = await fetch(`/urs/${uid}`).then(r => r.json());
    refreshDetailStatusBadge();
    renderApprovalPanel(document.querySelector('.urs-detail-panel[data-tab="approval"]'), ursState.currentURS);
    ursNotify({ type: "success", title: "Approval entry added", message: `"${action}" recorded.` });
  } catch (e) {
    ursNotify({
      type: "error", title: "Couldn't add approval entry", message: e.message,
      category: "Validation", retry: () => addApprovalEntry(uid),
    });
    if (btn) { btn.disabled = false; btn.textContent = "Add Entry"; }
  }
};

/* Keeps the detail view's header status badge in sync after any action
   that can change urs.status (approval entries, submit-for-review) — the
   badge is otherwise only set once when the detail view first loads. */
function refreshDetailStatusBadge() {
  const badge = document.getElementById("urs-detail-status");
  if (badge && ursState.currentURS) {
    badge.textContent = formatStatus(ursState.currentURS.status);
    badge.className = `urs-tag urs-tag-status ${ursState.currentURS.status}`;
  }
}

/* ── Versions Tab ───────────────────────────────────────────────────────────── */
function renderVersionsPanel(panel, urs) {
  panel.innerHTML = `
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <div class="urs-section-header" style="margin-bottom:0"><div class="section-icon"><span class=\'icon\' data-lucide=\'clock\'></span></div>Version History</div>
    <button class="btn-urs-primary" onclick="createVersionSnapshot(${urs.id})"><span class=\'icon\' data-lucide=\'camera\'></span> New Snapshot</button>
  </div>
  <div id="versions-list">
    <div class="urs-empty"><div class="urs-gen-spinner" style="margin:0 auto"></div></div>
  </div>`;
  loadVersionsList(urs.id);
}

async function loadVersionsList(uid) {
  const list = document.getElementById("versions-list");
  if (!list) return;
  try {
    const versions = await fetch(`/urs/${uid}/versions`).then(r => r.json());
    if (!versions.length) {
      list.innerHTML = `<div class="urs-empty"><p>No version snapshots yet.</p><p style="font-size:12px;margin-top:8px">Click <strong>New Snapshot</strong> to create one.</p></div>`;
      return;
    }
    list.innerHTML = `<div class="urs-version-list">` +
      versions.map(v => `
        <div class="urs-version-card">
          <div class="urs-version-badge">${v.version}</div>
          <div class="urs-version-info">
            <div class="urs-version-summary">${escHtml(v.change_summary || "Version snapshot")}</div>
            <div class="urs-version-meta">Rev ${v.revision} · ${formatStatus(v.status)} · ${v.req_count} requirements · By ${escHtml(v.created_by || "—")} · ${formatDate(v.created_at)}</div>
          </div>
        </div>`).join("") + `</div>`;
  } catch (e) {
    list.innerHTML = `<p style="color:var(--error)">Error: ${e.message}</p>`;
  }
}

window.createVersionSnapshot = async function (uid) {
  const summary = prompt("Enter change summary for this snapshot:", "Version snapshot");
  if (summary === null) return;
  // created_by comes from the authenticated user when available — only
  // falls back to a prompt in the rare case there's no session (matches
  // the same identity-derivation pattern used for approval entries).
  const user = window.PharmaAuth && PharmaAuth.getUser && PharmaAuth.getUser();
  const by = (user && (user.display_name || user.email)) || prompt("Your name:", "") || "System";
  try {
    const resp = await fetch(`/urs/${uid}/versions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ change_summary: summary, created_by: by }),
    });
    if (!resp.ok) throw new Error(`Server returned HTTP ${resp.status}`);
    ursNotify({ type: "success", title: "Version snapshot created", message: summary });
    loadVersionsList(uid);
  } catch (e) {
    ursNotify({
      type: "error", title: "Couldn't create version snapshot", message: e.message,
      category: "Database", retry: () => createVersionSnapshot(uid),
    });
  }
};

/* ── Traceability Tab ───────────────────────────────────────────────────────── */
function renderTraceabilityPanel(panel, urs) {
  const chain = [
    { icon: "<span class=\'icon\' data-lucide=\'clipboard-list\'></span>", name: "User Requirement Specification (URS)", sub: urs.urs_number || "This Document", status: "parent" },
    { icon: "<span class=\'icon\' data-lucide=\'alert-triangle\'></span>", name: "Risk Assessment", sub: "FMEA / ICH Q9", status: "" },
    { icon: "<span class=\'icon\' data-lucide=\'hard-hat\'></span>", name: "Design Qualification (DQ)", sub: "Design review & specifications", status: "" },
    { icon: "<span class=\'icon\' data-lucide=\'factory\'></span>", name: "Factory Acceptance Test (FAT)", sub: "Vendor site verification", status: "" },
    { icon: "<span class=\'icon\' data-lucide=\'truck\'></span>", name: "Site Acceptance Test (SAT)", sub: "Post-delivery verification", status: "" },
    { icon: "<span class=\'icon\' data-lucide=\'wrench\'></span>", name: "Installation Qualification (IQ)", sub: "Installation verification", status: "" },
    { icon: "<span class=\'icon\' data-lucide=\'settings\'></span>", name: "Operational Qualification (OQ)", sub: "Functional performance testing", status: "" },
    { icon: "<span class=\'icon\' data-lucide=\'bar-chart-3\'></span>", name: "Performance Qualification (PQ)", sub: "Process capability studies", status: "" },
    { icon: "<span class=\'icon\' data-lucide=\'link-2\'></span>", name: "Traceability Matrix", sub: "URS <span class=\'icon\' data-lucide=\'arrow-right\'></span> IQ/OQ/PQ linkage", status: "" },
    { icon: "<span class=\'icon\' data-lucide=\'file-text\'></span>", name: "Validation Report", sub: "Summary & conclusion", status: "" },
  ];

  panel.innerHTML = `
  <div class="urs-section-header"><div class="section-icon"><span class=\'icon\' data-lucide=\'link-2\'></span></div>Validation Lifecycle Traceability</div>
  <p style="font-size:13px;color:var(--text-muted);margin-bottom:20px">
    This URS is the parent document for the complete validation lifecycle. All downstream documents trace their requirements back to this URS.
  </p>
  <div class="urs-trace-chain">
    ${chain.map((item, i) => `
      ${i > 0 ? `<div class="urs-trace-arrow"><span class=\'icon\' data-lucide=\'arrow-down\'></span></div>` : ""}
      <div class="urs-trace-item">
        <div class="urs-trace-icon">${item.icon}</div>
        <div>
          <div class="urs-trace-name">${item.name}</div>
          <div class="urs-trace-sub">${item.sub}</div>
        </div>
        <div class="urs-trace-status ${item.status}">${item.status === "parent" ? "This Document" : "TBD"}</div>
      </div>`).join("")}
  </div>`;
}

/* ─────────────────────────────────────────────────────────────────────────────
   GLOBAL ACTIONS
────────────────────────────────────────────────────────────────────────────── */
// DOCX export — fetch + blob instead of a blind <a href> navigation.
// Iteration 2 fixed the download-auth bug (a browser navigation can't carry
// a custom Authorization header) with a session-cookie fallback, but a
// navigation still gives this code zero visibility into success/failure —
// it fires-and-forgets, so a 401/404/500 response was previously
// indistinguishable from a successful download; the user just... didn't
// get a file, with no explanation. fetch() carries the bearer token
// automatically (the same patched window.fetch every other call in this
// file already relies on) and lets this show real preparing/downloading/
// done/failed states with an actual error message and retry on failure.
window.exportURSDocx = async function (uid, ursNum, btnEl) {
  const btn = btnEl || (typeof event !== "undefined" && event.currentTarget) || null;
  const setState = (state) => { if (btn) btn.dataset.exportState = state; };

  setState("preparing");
  try {
    const resp = await fetch(`/urs/${uid}/export/docx`);
    if (!resp.ok) {
      let message = `Server returned HTTP ${resp.status}`;
      try {
        const body = await resp.json();
        if (body && body.error) message = body.error;
      } catch (e) { /* response wasn't JSON — keep the generic message */ }
      throw new Error(message);
    }

    setState("downloading");
    const blob = await resp.blob();
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = `URS_${ursNum || uid}.docx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);

    setState("done");
    ursNotify({ type: "success", title: "DOCX ready", message: `URS_${ursNum || uid}.docx downloaded.` });
    setTimeout(() => setState("idle"), 2000);
  } catch (e) {
    setState("idle");
    ursNotify({
      type: "error", title: "DOCX export failed", message: e.message,
      category: "Download", retry: () => exportURSDocx(uid, ursNum, btn),
    });
  }
};

window.deleteURS = async function (uid) {
  if (!confirm("Delete this URS? This action cannot be undone.")) return;
  try {
    const resp = await fetch(`/urs/${uid}`, { method: "DELETE" });
    if (!resp.ok) throw new Error(`Server returned HTTP ${resp.status}`);
    ursNotify({ type: "success", title: "URS deleted", message: `URS #${uid} was deleted.` });
    loadURSList();
  } catch (e) {
    ursNotify({
      type: "error", title: "Couldn't delete URS", message: e.message,
      category: "Database", retry: () => deleteURS(uid),
    });
  }
};

window.submitForReview = async function (uid) {
  // Prevents an obviously-invalid submit (e.g. re-clicking on an already
  // Under-Review/Approved document) without waiting on a round-trip — the
  // backend still validates independently either way.
  if (ursState.currentURS && !ursValidActionsFor(ursState.currentURS.status).includes("Submitted for Review")) {
    ursNotify({
      type: "warning", title: "Already past Draft",
      message: `This document is ${formatStatus(ursState.currentURS.status)} and can't be re-submitted for review from here.`,
      category: "Validation",
    });
    return;
  }
  const user = window.PharmaAuth && PharmaAuth.getUser && PharmaAuth.getUser();
  const name = (user && (user.display_name || user.email)) || prompt("Your name (submitter):", "") || "";
  if (!name) return;
  try {
    const resp = await fetch(`/urs/${uid}/approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "Submitted for Review", performed_by: name, role: (user && user.role) || "Author", comments: "" }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.error || `Server returned HTTP ${resp.status}`);
    }
    ursState.currentURS = await fetch(`/urs/${uid}`).then(r => r.json());
    refreshDetailStatusBadge();
    ursNotify({ type: "success", title: "Submitted for review", message: "This URS has been submitted for review." });
  } catch (e) {
    ursNotify({
      type: "error", title: "Couldn't submit for review", message: e.message,
      category: "Validation", retry: () => submitForReview(uid),
    });
  }
};

window.showURSApprovalQueue = function () {
  fetchAndRenderURSList({ status: "under_review" });
  showView("view-urs-list");
};

/* ─────────────────────────────────────────────────────────────────────────────
   HELPERS
────────────────────────────────────────────────────────────────────────────── */
function escHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatStatus(s) {
  const map = {
    draft: "Draft", under_review: "Under Review",
    pending_approval: "Pending Approval", approved: "Approved", obsolete: "Obsolete",
  };
  return map[s] || s || "Draft";
}

function formatDate(ts) {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return ts; }
}

function infoRow(label, value) {
  return `<div class="urs-info-row"><label>${label}</label><span>${escHtml(String(value || "—"))}</span></div>`;
}
