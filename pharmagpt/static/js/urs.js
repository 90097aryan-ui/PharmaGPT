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

/* ── Toast ──────────────────────────────────────────────────────────────────── */
function ursToast(msg, type = "info") {
  let toast = document.getElementById("urs-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "urs-toast";
    toast.className = "urs-toast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.className = `urs-toast ${type} show`;
  setTimeout(() => { toast.classList.remove("show"); }, 3000);
}

/* ─────────────────────────────────────────────────────────────────────────────
   DASHBOARD
────────────────────────────────────────────────────────────────────────────── */
window.loadURSDashboard = async function () {
  showView("view-urs-dashboard");
  const body = document.getElementById("urs-dash-body");
  if (!body) return;
  body.innerHTML = '<div class="urs-empty"><div class="urs-gen-spinner" style="margin:40px auto;width:32px;height:32px;border-width:4px"></div></div>';

  try {
    const [stats, allURS] = await Promise.all([
      fetch("/urs/dashboard").then(r => r.json()),
      fetch("/urs/").then(r => r.json()),
    ]);
    body.innerHTML = buildDashboardHTML(stats, allURS);
  } catch (e) {
    body.innerHTML = `<div class="urs-empty"><p>Failed to load dashboard: ${e.message}</p></div>`;
  }
};

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
  const grid = document.getElementById("urs-list-grid");
  const empty = document.getElementById("urs-list-empty");
  if (!grid) return;
  grid.innerHTML = "";
  if (empty) empty.style.display = "none";

  const params = new URLSearchParams(filters);
  try {
    const data = await fetch(`/urs/?${params}`).then(r => r.json());
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
          <button class="btn-urs-outline" onclick="event.stopPropagation();exportURSDocx(${u.id}, '${escHtml(u.urs_number || 'URS')}')"><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span> DOCX</button>
          <button class="btn-urs-danger" onclick="event.stopPropagation();deleteURS(${u.id})"><span class=\'icon\' data-lucide=\'trash-2\'></span></button>
        </div>`;
      card.addEventListener("click", () => openURS(u.id));
      grid.appendChild(card);
    });
  } catch (e) {
    grid.innerHTML = `<p style="color:var(--error);font-size:13px">Error: ${e.message}</p>`;
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
function renderStep2(body) {
  const d = ursState.wizardData;
  const today = new Date().toISOString().split("T")[0];
  body.innerHTML = `
  <div class="urs-section-header"><div class="section-icon"><span class=\'icon\' data-lucide=\'pencil-line\'></span></div>Project Information</div>
  <div class="urs-form-grid">
    <div class="urs-field">
      <label class="urs-label">URS Number <span class="req-star">*</span></label>
      <input class="urs-input" id="w-urs-number" value="${d.urs_number || ''}" placeholder="e.g. URS-2025-001">
    </div>
    <div class="urs-field">
      <label class="urs-label">Document Number</label>
      <input class="urs-input" id="w-doc-number" value="${d.doc_number || ''}" placeholder="e.g. QA-URS-001">
    </div>
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
    <div class="urs-field">
      <label class="urs-label">Revision</label>
      <input class="urs-input" id="w-revision" value="${d.revision || 'A'}" placeholder="A">
    </div>
    <div class="urs-field">
      <label class="urs-label">Effective Date</label>
      <input class="urs-input" type="date" id="w-effective-date" value="${d.effective_date || today}">
    </div>
    <div class="urs-field">
      <label class="urs-label">Prepared By</label>
      <input class="urs-input" id="w-prepared-by" value="${d.prepared_by || ''}" placeholder="Full name">
    </div>
    <div class="urs-field">
      <label class="urs-label">Reviewed By</label>
      <input class="urs-input" id="w-reviewed-by" value="${d.reviewed_by || ''}" placeholder="Full name">
    </div>
    <div class="urs-field">
      <label class="urs-label">Approved By</label>
      <input class="urs-input" id="w-approved-by" value="${d.approved_by || ''}" placeholder="Full name">
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
  ursState.wizardData.urs_number     = document.getElementById("w-urs-number")?.value.trim() || "";
  ursState.wizardData.doc_number     = document.getElementById("w-doc-number")?.value.trim() || "";
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
  ursState.wizardData.revision       = document.getElementById("w-revision")?.value.trim() || "A";
  ursState.wizardData.effective_date = document.getElementById("w-effective-date")?.value || "";
  ursState.wizardData.prepared_by    = document.getElementById("w-prepared-by")?.value.trim() || "";
  ursState.wizardData.reviewed_by    = document.getElementById("w-reviewed-by")?.value.trim() || "";
  ursState.wizardData.approved_by    = document.getElementById("w-approved-by")?.value.trim() || "";
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

  <div class="urs-gen-progress" id="urs-gen-progress">
    <div class="urs-gen-spinner"></div>
    <div class="urs-gen-text" id="urs-gen-text">Generating requirements…</div>
    <div class="urs-gen-count" id="urs-gen-count">0 requirements generated</div>
  </div>

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

window.runAIGeneration = async function () {
  if (!ursState.currentURS) await createURSRecord();
  if (!ursState.currentURS) return;

  const sections = [...document.querySelectorAll('input[name="section"]:checked')].map(cb => cb.value);
  if (!sections.length) { ursToast("Select at least one section", "error"); return; }

  const progress = document.getElementById("urs-gen-progress");
  const genText = document.getElementById("urs-gen-text");
  const genCount = document.getElementById("urs-gen-count");
  const genBtn = document.getElementById("generate-btn");

  progress.classList.add("visible");
  genBtn.disabled = true;
  let charCount = 0;

  try {
    const res = await fetch(`/urs/${ursState.currentURS.id}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sections, ...ursState.wizardData }),
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let reqCount = 0;
    let parseError = null;
    let streamError = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const msg = JSON.parse(line.slice(6));
          if (msg.chunk) {
            charCount += msg.chunk.length;
            genText.textContent = `Generating requirements… (${charCount} chars)`;
          }
          if (msg.done) {
            reqCount = msg.count || 0;
            parseError = msg.parse_error || null;
            genCount.textContent = `${reqCount} requirements generated`;
            genText.textContent = parseError ? "Generation finished, but parsing failed." : "Generation complete!";
          }
          if (msg.error) {
            streamError = msg.error;
            genText.textContent = `Error: ${msg.error}`;
          }
        } catch (e) {}
      }
    }

    ursState.requirements = await fetch(`/urs/${ursState.currentURS.id}/requirements`).then(r => r.json());

    if (streamError) {
      ursToast(`Generation error: ${streamError}`, "error");
      genBtn.disabled = false;
    } else if (parseError || reqCount === 0) {
      ursToast(`AI returned no usable requirements (${parseError || "empty result"}). Try again, or add requirements manually / from the library.`, "error");
      genBtn.disabled = false;
    } else {
      ursToast(`${reqCount} requirements generated`, "success");
      setTimeout(() => wizardGoTo(4), 800);
    }
  } catch (e) {
    genText.textContent = `Error: ${e.message}`;
    ursToast(`Generation error: ${e.message}`, "error");
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
      <div class="urs-info-card-title">Document Details</div>
      <div class="urs-info-row"><label>URS Number</label><span>${escHtml(urs.urs_number || ursState.wizardData.urs_number || "—")}</span></div>
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
    <button class="btn-urs-outline" onclick="exportURSDocx(${urs.id}, '${escHtml(urs.urs_number || 'URS')}')"><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span> Export DOCX</button>
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
  <div style="display:flex;gap:10px;margin-top:4px;flex-wrap:wrap">
    <button class="btn-urs-primary" onclick="exportURSDocx(${urs.id}, '${escHtml(urs.urs_number||'URS')}')"><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span> Export DOCX</button>
    <button class="btn-urs-outline" onclick="submitForReview(${urs.id})"><span class=\'icon\' data-lucide=\'mail\'></span> Submit for Review</button>
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
function renderApprovalPanel(panel, urs) {
  panel.innerHTML = `
  <div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
    <div style="flex:1;min-width:280px">
      <div class="urs-section-header" style="margin-bottom:16px"><div class="section-icon"><span class=\'icon\' data-lucide=\'check-circle-2\'></span></div>Approval Trail</div>
      <div class="urs-approval-timeline" id="approval-timeline">
        <div class="urs-empty" style="padding:20px"><div class="urs-gen-spinner" style="margin:0 auto"></div></div>
      </div>
    </div>
    <div style="width:280px;flex-shrink:0">
      <div class="urs-section-header" style="margin-bottom:16px"><div class="section-icon"><span class=\'icon\' data-lucide=\'plus\'></span></div>Add Entry</div>
      <div class="urs-field" style="margin-bottom:12px">
        <label class="urs-label">Action</label>
        <select class="urs-select" id="approval-action">
          <option>Submitted for Review</option>
          <option>Review Complete</option>
          <option>Submitted for Approval</option>
          <option>Approved</option>
          <option>Rejected</option>
          <option>Obsolete</option>
        </select>
      </div>
      <div class="urs-field" style="margin-bottom:12px">
        <label class="urs-label">Name</label>
        <input class="urs-input" id="approval-name" placeholder="Your name">
      </div>
      <div class="urs-field" style="margin-bottom:12px">
        <label class="urs-label">Role</label>
        <input class="urs-input" id="approval-role" placeholder="e.g. QA Manager">
      </div>
      <div class="urs-field" style="margin-bottom:12px">
        <label class="urs-label">Comments</label>
        <textarea class="urs-textarea" id="approval-comments" placeholder="Optional comments…"></textarea>
      </div>
      <button class="btn-urs-primary" style="width:100%" onclick="addApprovalEntry(${urs.id})">Add Entry</button>
    </div>
  </div>`;
  loadApprovalTrail(urs.id);
}

async function loadApprovalTrail(uid) {
  const timeline = document.getElementById("approval-timeline");
  if (!timeline) return;
  try {
    const entries = await fetch(`/urs/${uid}/approval`).then(r => r.json());
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
    timeline.innerHTML = `<p style="color:var(--error)">Error loading trail</p>`;
  }
}

window.addApprovalEntry = async function (uid) {
  const action = document.getElementById("approval-action")?.value;
  const name = document.getElementById("approval-name")?.value.trim();
  const role = document.getElementById("approval-role")?.value.trim();
  const comments = document.getElementById("approval-comments")?.value.trim();
  if (!name) { ursToast("Name is required", "error"); return; }
  try {
    await fetch(`/urs/${uid}/approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, performed_by: name, role, comments }),
    });
    // Refresh current URS state and re-render
    ursState.currentURS = await fetch(`/urs/${uid}`).then(r => r.json());
    loadApprovalTrail(uid);
 ursToast("Approval entry added", "success");
  } catch (e) {
    ursToast(`Error: ${e.message}`, "error");
  }
};

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
  const by = prompt("Your name:", "") || "System";
  try {
    await fetch(`/urs/${uid}/versions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ change_summary: summary, created_by: by }),
    });
 ursToast("Version snapshot created", "success");
    loadVersionsList(uid);
  } catch (e) {
    ursToast(`Error: ${e.message}`, "error");
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
window.exportURSDocx = function (uid, ursNum) {
  const link = document.createElement("a");
  link.href = `/urs/${uid}/export/docx`;
  link.download = `URS_${ursNum || uid}.docx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
 ursToast("Downloading DOCX…", "info");
};

window.deleteURS = async function (uid) {
  if (!confirm("Delete this URS? This action cannot be undone.")) return;
  try {
    await fetch(`/urs/${uid}`, { method: "DELETE" });
 ursToast("URS deleted", "success");
    loadURSList();
  } catch (e) {
    ursToast(`Error: ${e.message}`, "error");
  }
};

window.submitForReview = async function (uid) {
  const name = prompt("Your name (submitter):", "") || "";
  if (!name) return;
  try {
    await fetch(`/urs/${uid}/approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "Submitted for Review", performed_by: name, role: "Author", comments: "" }),
    });
 ursToast("URS submitted for review", "success");
    ursState.currentURS = await fetch(`/urs/${uid}`).then(r => r.json());
  } catch (e) {
    ursToast(`Error: ${e.message}`, "error");
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
