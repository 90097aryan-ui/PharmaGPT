/**
 * risk.js — Risk Management Suite frontend for PharmaGPT
 * Handles all views: Dashboard, New Assessment, Risk Library,
 * Templates, Reports, Review & Approval, AI Assistant.
 */

// ── State ─────────────────────────────────────────────────────────────────────
const RiskState = {
  currentAssessment: null,   // Full assessment object
  currentItems: [],          // Risk item rows
  wizardStep: 1,
  selectedType: null,
  selectedSubtype: null,
  selectedMethodology: null,
  isGenerating: false,
  filterParams: {},
  assessments: [],           // Loaded list
};

// ── Constants ─────────────────────────────────────────────────────────────────

const ASSESSMENT_TYPES = {
  validation: {
    icon: "<span class=\'icon\' data-lucide=\'microscope\'></span>", label: "Validation Risk",
    subtypes: [
      "Equipment Qualification", "Utility Qualification", "Cleaning Validation",
      "Process Validation", "Computer System Validation (CSV)",
    ],
  },
  manufacturing: {
    icon: "<span class=\'icon\' data-lucide=\'factory\'></span>", label: "Manufacturing Risk",
    subtypes: ["Process", "Packaging", "Line Clearance", "Material Handling", "Batch Manufacturing"],
  },
  engineering: {
    icon: "<span class=\'icon\' data-lucide=\'settings\'></span>", label: "Engineering Risk",
    subtypes: ["HVAC", "Water System", "Compressed Air", "Steam", "Facility Modification"],
  },
  quality: {
    icon: "<span class=\'icon\' data-lucide=\'clipboard-list\'></span>", label: "Quality Risk",
    subtypes: ["Deviation", "CAPA", "Change Control", "OOS", "OOT", "Complaint Investigation", "Audit Observation"],
  },
  warehouse: {
    icon: "<span class=\'icon\' data-lucide=\'store\'></span>", label: "Warehouse Risk",
    subtypes: ["Storage", "Dispensing", "Sampling", "Distribution"],
  },
  misc: {
    icon: "<span class=\'icon\' data-lucide=\'pencil-line\'></span>", label: "Miscellaneous Risk",
    subtypes: ["General Activity", "Custom"],
  },
};

const METHODOLOGIES = [
  { key: "FMEA",        name: "FMEA",         desc: "Failure Mode & Effects Analysis" },
  { key: "HACCP",       name: "HACCP",         desc: "Hazard Analysis & Critical Control Points" },
  { key: "HAZOP",       name: "HAZOP",         desc: "Hazard and Operability Study" },
  { key: "Risk Matrix", name: "Risk Matrix",   desc: "Probability × Impact Matrix" },
  { key: "What-If",     name: "What-If / PHA", desc: "What-If Analysis / Preliminary Hazard Analysis" },
  { key: "FTA",         name: "FTA",           desc: "Fault Tree Analysis" },
  { key: "Custom",      name: "Custom",        desc: "Flexible Custom Assessment" },
];

const TEMPLATES = [
  { id: "eq_autoclave",   icon: "<span class=\'icon\' data-lucide=\'flame\'></span>",  name: "Autoclave Qualification",    type: "validation", sub: "Equipment Qualification", method: "FMEA",    dept: "Engineering" },
  { id: "eq_hvac",        icon: "<span class=\'icon\' data-lucide=\'wind\'></span>", name: "HVAC Risk Assessment",       type: "engineering",sub: "HVAC",                   method: "FMEA",    dept: "Engineering" },
  { id: "eq_water",       icon: "<span class=\'icon\' data-lucide=\'droplet\'></span>",  name: "Water System Risk",          type: "engineering",sub: "Water System",            method: "FMEA",    dept: "Engineering" },
  { id: "eq_filling",     icon: "<span class=\"icon\" data-lucide=\"package\"></span>",  name: "Bottle Filling Line",        type: "manufacturing",sub: "Packaging",             method: "HACCP",   dept: "Manufacturing" },
  { id: "eq_blister",     icon: "<span class=\'icon\' data-lucide=\'pill\'></span>",  name: "Blister Packing FMEA",      type: "manufacturing",sub: "Packaging",             method: "FMEA",    dept: "Manufacturing" },
  { id: "eq_compression", icon: "<span class=\'icon\' data-lucide=\'wrench\'></span>",  name: "Tablet Compression",        type: "manufacturing",sub: "Process",               method: "FMEA",    dept: "Manufacturing" },
  { id: "eq_coating",     icon: "<span class=\'icon\' data-lucide=\'palette\'></span>",  name: "Tablet Coating Process",    type: "manufacturing",sub: "Process",               method: "FMEA",    dept: "Manufacturing" },
  { id: "csv_risk",       icon: "<span class=\'icon\' data-lucide=\'laptop\'></span>",  name: "CSV Risk Assessment",        type: "validation", sub: "Computer System Validation (CSV)", method: "FMEA", dept: "IT/QA" },
  { id: "cleaning_val",   icon: "<span class=\'icon\' data-lucide=\'droplet\'></span>",  name: "Cleaning Validation Risk",  type: "validation", sub: "Cleaning Validation",    method: "FMEA",    dept: "Manufacturing" },
  { id: "deviation",      icon: "<span class=\'icon\' data-lucide=\'zap\'></span>",  name: "Deviation Risk Assessment", type: "quality",    sub: "Deviation",              method: "Risk Matrix", dept: "Quality" },
  { id: "capa",           icon: "<span class=\'icon\' data-lucide=\'repeat\'></span>",  name: "CAPA Risk Assessment",      type: "quality",    sub: "CAPA",                   method: "Risk Matrix", dept: "Quality" },
  { id: "change_ctrl",    icon: "<span class=\'icon\' data-lucide=\'shuffle\'></span>",  name: "Change Control Risk",       type: "quality",    sub: "Change Control",         method: "Risk Matrix", dept: "Quality" },
  { id: "warehouse",      icon: "<span class=\'icon\' data-lucide=\'package\'></span>",  name: "Warehouse Risk Assessment", type: "warehouse",  sub: "Storage",                method: "FMEA",    dept: "Warehouse" },
  { id: "process_val",    icon: "<span class=\'icon\' data-lucide=\'flask-conical\'></span>",  name: "Process Validation Risk",   type: "validation", sub: "Process Validation",     method: "FMEA",    dept: "Manufacturing" },
  { id: "general",        icon: "<span class=\'icon\' data-lucide=\'file-text\'></span>",  name: "General Risk Assessment",   type: "misc",       sub: "General Activity",       method: "Custom",  dept: "" },
];

const LIBRARY_CATEGORIES = [
  "All", "Manufacturing", "Packaging", "Validation", "Engineering",
  "Utilities", "Warehouse", "Quality", "Cleaning", "Calibration", "Laboratory",
];


// ── Initialisation ────────────────────────────────────────────────────────────

window.initRisk = function () {
  loadRiskDashboard();
};

function showRiskView(viewId) {
  document.querySelectorAll("main[id^='view-risk-']").forEach(v => v.style.display = "none");
  const v = document.getElementById(viewId);
  if (v) v.style.display = "flex";

  // Update sidebar active state
  document.querySelectorAll(".risk-sub-item").forEach(el => el.classList.remove("active"));
  const navMap = {
    "view-risk-dashboard": "risk-nav-dashboard",
    "view-risk-new":       "risk-nav-new",
    "view-risk-library":   "risk-nav-library",
    "view-risk-templates": "risk-nav-templates",
    "view-risk-reports":   "risk-nav-reports",
    "view-risk-approval":  "risk-nav-approval",
    "view-risk-assistant": "risk-nav-assistant",
  };
  const navEl = document.getElementById(navMap[viewId]);
  if (navEl) navEl.classList.add("active");
}


// ── Dashboard ─────────────────────────────────────────────────────────────────

async function loadRiskDashboard() {
  showRiskView("view-risk-dashboard");
  const body = document.getElementById("risk-dash-body");
  if (!body) return;
  body.innerHTML = `<div class="risk-ai-generating"><div class="spinner"></div> Loading dashboard…</div>`;

  try {
    const res = await fetch("/risk/dashboard");
    const stats = await res.json();
    renderDashboard(stats);
  } catch (e) {
    body.innerHTML = `<div class="risk-empty"><p>Failed to load dashboard. ${e.message}</p></div>`;
  }
}

function renderDashboard(stats) {
  const body = document.getElementById("risk-dash-body");
  const totalOpen = (stats.draft || 0) + (stats.in_review || 0) + (stats.in_progress || 0);
  const pending_approval = stats.in_review || 0;

  body.innerHTML = `
    <div class="risk-stats-grid">
      ${statCard("<span class=\'icon\' data-lucide=\'bar-chart-3\'></span>", stats.total || 0, "Total Assessments", "info")}
      ${statCard("<span class=\'icon\' data-lucide=\'pencil-line\'></span>", stats.draft || 0, "Draft", "info")}
      ${statCard("<span class=\'icon\' data-lucide=\'search\'></span>", pending_approval, "Pending Approval", "medium")}
      ${statCard("<span class=\'icon\' data-lucide=\'check-circle-2\'></span>", stats.approved || 0, "Approved", "low")}
      ${statCard("<span class=\'icon\' data-lucide=\'circle\'></span>", stats.critical || 0, "Critical Priority", "critical")}
      ${statCard("<span class=\'icon\' data-lucide=\'circle\'></span>", stats.high || 0, "High Priority", "high")}
      ${statCard("<span class=\'icon\' data-lucide=\'alert-triangle\'></span>", stats.high_rpn || 0, "High RPN Items", "high")}
      ${statCard("<span class=\'icon\' data-lucide=\'wrench\'></span>", stats.pending_actions || 0, "Pending Actions", "medium")}
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px">
      ${renderHeatMap()}
      ${renderTypeBreakdown(stats.by_type || {})}
    </div>

    <div class="risk-section-card">
      <div class="risk-section-title"><span class=\'icon\' data-lucide=\'clock\'></span> Recent Assessments</div>
      <div class="risk-section-body">
        ${(stats.recent || []).length === 0 ?
          `<div class="risk-empty"><div class="risk-empty-icon"><span class=\'icon\' data-lucide=\'clipboard-list\'></span></div><h3>No assessments yet</h3><p>Create your first risk assessment to get started.</p></div>` :
          `<div class="assessment-list">${(stats.recent || []).map(a => assessmentCardHtml(a)).join("")}</div>`
        }
      </div>
    </div>
  `;

  // Bind recent assessment card clicks
  body.querySelectorAll(".assessment-card[data-aid]").forEach(el => {
    el.addEventListener("click", () => openAssessment(parseInt(el.dataset.aid)));
  });
}

function statCard(icon, value, label, cls) {
  return `<div class="risk-stat-card ${cls}">
    <div class="stat-value">${value}</div>
    <div class="stat-label">${icon} ${label}</div>
  </div>`;
}

function renderHeatMap() {
  const labels = ["Negligible", "Minor", "Moderate", "Major", "Catastrophic"];
  const cells = [];
  for (let impact = 5; impact >= 1; impact--) {
    for (let prob = 1; prob <= 5; prob++) {
      const score = impact * prob;
      let cls = "heat-low";
      if (score >= 15) cls = "heat-critical";
      else if (score >= 10) cls = "heat-high";
      else if (score >= 5)  cls = "heat-medium";
      cells.push(`<div class="heat-cell ${cls}" title="Prob:${prob} × Impact:${impact} = ${score}">${score}</div>`);
    }
  }
  return `<div class="risk-section-card">
    <div class="risk-section-title"><span class=\'icon\' data-lucide=\'thermometer\'></span> Risk Heat Map</div>
    <div class="risk-section-body">
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">Probability (<span class=\'icon\' data-lucide=\'arrow-right\'></span>) × Impact (<span class=\'icon\' data-lucide=\'arrow-up\'></span>)</div>
      <div class="risk-heat-map">${cells.join("")}</div>
      <div style="display:flex;gap:12px;margin-top:10px;font-size:11px;flex-wrap:wrap">
        <span style="display:flex;align-items:center;gap:4px"><span style="width:12px;height:12px;border-radius:3px;background:#E8F2EA;display:inline-block"></span>Low (1–4)</span>
        <span style="display:flex;align-items:center;gap:4px"><span style="width:12px;height:12px;border-radius:3px;background:#FFF4E5;display:inline-block"></span>Medium (5–9)</span>
        <span style="display:flex;align-items:center;gap:4px"><span style="width:12px;height:12px;border-radius:3px;background:#FFF4E5;display:inline-block"></span>High (10–14)</span>
        <span style="display:flex;align-items:center;gap:4px"><span style="width:12px;height:12px;border-radius:3px;background:#F2D8D6;display:inline-block"></span>Critical (15–25)</span>
      </div>
    </div>
  </div>`;
}

function renderTypeBreakdown(byType) {
  const entries = Object.entries(byType);
  const total = entries.reduce((s, [, c]) => s + c, 0) || 1;
  const colors = { validation: "#8A6B52", manufacturing: "#A97D2E", engineering: "#66615B",
                   quality: "#5F8A61", warehouse: "#8A6B52", misc: "#66615B" };
  const rows = entries.map(([type, count]) => {
    const pct = Math.round((count / total) * 100);
    const color = colors[type] || "#8A6B52";
    return `<div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px">
        <span style="text-transform:capitalize;font-weight:600">${type}</span>
        <span style="color:var(--text-muted)">${count} (${pct}%)</span>
      </div>
      <div style="background:var(--risk-border);border-radius:4px;height:8px;overflow:hidden">
        <div style="width:${pct}%;height:100%;background:${color};border-radius:4px;transition:width 0.5s"></div>
      </div>
    </div>`;
  });
  return `<div class="risk-section-card">
    <div class="risk-section-title"><span class=\'icon\' data-lucide=\'bar-chart-3\'></span> Assessments by Type</div>
    <div class="risk-section-body">
      ${rows.length ? rows.join("") : `<div class="risk-empty"><p>No data yet.</p></div>`}
    </div>
  </div>`;
}

function assessmentCardHtml(a) {
  const priorityCls = (a.priority || "Medium").toLowerCase();
  const statusCls = (a.status || "Draft").toLowerCase().replace(" ", "-");
  const typeInfo = ASSESSMENT_TYPES[a.assessment_type] || { icon: "<span class=\'icon\' data-lucide=\'file-text\'></span>" };
  return `<div class="assessment-card" data-aid="${a.id}">
    <div class="assessment-card-icon">${typeInfo.icon}</div>
    <div class="assessment-card-body">
      <div class="assessment-card-title">${esc(a.title)}</div>
      <div class="assessment-card-meta">
        <span>${esc(a.assessment_type || "—")}</span>
        <span>${esc(a.methodology || "—")}</span>
        <span>${esc(a.department || "—")}</span>
        <span>${esc(a.assessment_date || a.created_at?.split("T")[0] || "—")}</span>
      </div>
    </div>
    <div class="assessment-card-actions">
      <span class="badge badge-${priorityCls}">${a.priority || "Medium"}</span>
      <span class="badge badge-${statusCls}">${a.status || "Draft"}</span>
    </div>
  </div>`;
}


// ── Assessment List (New Assessment view reused for listing) ──────────────────

async function loadAssessmentList() {
  showRiskView("view-risk-new");
  const body = document.getElementById("risk-list-body");
  if (!body) return;
  body.innerHTML = `<div class="risk-ai-generating"><div class="spinner"></div> Loading assessments…</div>`;

  const params = new URLSearchParams(RiskState.filterParams);
  try {
    const res = await fetch(`/risk/assessments?${params}`);
    const assessments = await res.json();
    RiskState.assessments = assessments;
    renderAssessmentList(assessments);
  } catch (e) {
    body.innerHTML = `<div class="risk-empty"><p>Error loading. ${e.message}</p></div>`;
  }
}

function renderAssessmentList(assessments) {
  const body = document.getElementById("risk-list-body");
  if (!assessments.length) {
    body.innerHTML = `<div class="risk-empty">
      <div class="risk-empty-icon"><span class=\'icon\' data-lucide=\'clipboard-list\'></span></div>
      <h3>No assessments found</h3>
      <p>Create your first risk assessment using the wizard.</p>
      <button class="btn-risk-primary" style="margin-top:16px" onclick="startNewWizard()">＋ New Assessment</button>
    </div>`;
    return;
  }
  body.innerHTML = `<div class="assessment-list">${assessments.map(a => assessmentCardHtml(a)).join("")}</div>`;
  body.querySelectorAll(".assessment-card[data-aid]").forEach(el => {
    el.addEventListener("click", () => openAssessment(parseInt(el.dataset.aid)));
  });
}

async function applyRiskFilters() {
  const q = document.getElementById("risk-search-input")?.value || "";
  const type = document.getElementById("risk-filter-type")?.value || "";
  const method = document.getElementById("risk-filter-method")?.value || "";
  const status = document.getElementById("risk-filter-status")?.value || "";
  RiskState.filterParams = {};
  if (q) RiskState.filterParams.q = q;
  if (type) RiskState.filterParams.type = type;
  if (method) RiskState.filterParams.methodology = method;
  if (status) RiskState.filterParams.status = status;
  await loadAssessmentList();
}
window.applyRiskFilters = applyRiskFilters;


// ── Wizard ────────────────────────────────────────────────────────────────────

function startNewWizard() {
  RiskState.wizardStep = 1;
  RiskState.selectedType = null;
  RiskState.selectedSubtype = null;
  RiskState.selectedMethodology = null;
  RiskState.currentAssessment = null;
  RiskState.currentItems = [];

  showRiskView("view-risk-new");

  const listView = document.getElementById("risk-list-view");
  const wizardView = document.getElementById("risk-wizard-view");
  if (listView) listView.style.display = "none";
  if (wizardView) wizardView.style.display = "block";

  riskRenderWizardStep(1);
}
window.startNewWizard = startNewWizard;

function riskRenderWizardStep(step) {
  RiskState.wizardStep = step;
  updateWizardStepIndicators(step);

  const panels = document.querySelectorAll(".wizard-panel");
  panels.forEach(p => p.classList.remove("active"));
  const active = document.getElementById(`wizard-panel-${step}`);
  if (active) active.classList.add("active");

  // Populate dynamic content per step
  if (step === 1) renderTypeSelector();
  if (step === 3) renderMethodologySelector();
}

function updateWizardStepIndicators(step) {
  document.querySelectorAll(".wizard-step").forEach((el, i) => {
    el.classList.remove("active", "done");
    if (i + 1 < step) el.classList.add("done");
    else if (i + 1 === step) el.classList.add("active");
  });
}

function renderTypeSelector() {
  const container = document.getElementById("risk-type-selector");
  if (!container) return;
  container.innerHTML = Object.entries(ASSESSMENT_TYPES).map(([key, val]) => `
    <div class="risk-type-card${RiskState.selectedType === key ? " selected" : ""}"
         onclick="selectRiskType('${key}')">
      <div class="rtc-icon">${val.icon}</div>
      <div class="rtc-name">${val.label}</div>
      <div class="rtc-sub">${val.subtypes.slice(0, 3).join(" · ")}</div>
    </div>
  `).join("");
}

window.selectRiskType = function (key) {
  RiskState.selectedType = key;
  RiskState.selectedSubtype = null;
  renderTypeSelector();
  renderSubtypeSelector(key);
};

function renderSubtypeSelector(key) {
  const container = document.getElementById("risk-subtype-selector");
  if (!container) return;
  const info = ASSESSMENT_TYPES[key];
  if (!info) { container.innerHTML = ""; return; }
  container.innerHTML = `<div style="margin-top:16px">
    <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:0.4px">Select Sub-type</div>
    <div style="display:flex;flex-wrap:wrap;gap:8px">
      ${info.subtypes.map(s => `
        <button class="btn-risk-secondary" style="font-size:12px;padding:6px 14px;${RiskState.selectedSubtype === s ? "border-color:var(--risk-accent);background:#F1ECE6;color:var(--risk-accent)" : ""}"
                onclick="selectSubtype('${s.replace(/'/g,"\\'")}')">
          ${s}
        </button>
      `).join("")}
    </div>
  </div>`;
}

window.selectSubtype = function (s) {
  RiskState.selectedSubtype = s;
  renderSubtypeSelector(RiskState.selectedType);
};

function renderMethodologySelector() {
  const container = document.getElementById("risk-methodology-selector");
  if (!container) return;
  container.innerHTML = METHODOLOGIES.map(m => `
    <div class="methodology-card${RiskState.selectedMethodology === m.key ? " selected" : ""}"
         onclick="selectMethodology('${m.key.replace(/'/g,"\\'")}')">
      <div class="mc-name">${m.name}</div>
      <div class="mc-desc">${m.desc}</div>
    </div>
  `).join("");
}

window.selectMethodology = function (key) {
  RiskState.selectedMethodology = key;
  renderMethodologySelector();
};

window.wizardNext = function () {
  const step = RiskState.wizardStep;
  if (step === 1) {
    if (!RiskState.selectedType) { alert("Please select a risk type."); return; }
    riskRenderWizardStep(2);
  } else if (step === 2) {
    riskRenderWizardStep(3);
  } else if (step === 3) {
    if (!RiskState.selectedMethodology) { alert("Please select a methodology."); return; }
    riskRenderWizardStep(4);
  } else if (step === 4) {
    riskRenderWizardStep(5);
  }
};

window.wizardBack = function () {
  if (RiskState.wizardStep > 1) riskRenderWizardStep(RiskState.wizardStep - 1);
};

window.createAndOpenAssessment = async function () {
  const form = document.getElementById("wizard-info-form");
  if (!form) return;

  const data = {
    title: form.title?.value?.trim() || "Untitled Assessment",
    assessment_type: RiskState.selectedType || "",
    assessment_subtype: RiskState.selectedSubtype || "",
    methodology: RiskState.selectedMethodology || "FMEA",
    department: form.department?.value?.trim() || "",
    area: form.area?.value?.trim() || "",
    equipment: form.equipment?.value?.trim() || "",
    product: form.product?.value?.trim() || "",
    process: form.process?.value?.trim() || "",
    protocol_reference: form.protocol_reference?.value?.trim() || "",
    change_control_reference: form.change_control_reference?.value?.trim() || "",
    assessment_owner: form.assessment_owner?.value?.trim() || "",
    reviewer: form.reviewer?.value?.trim() || "",
    approver: form.approver?.value?.trim() || "",
    assessment_date: form.assessment_date?.value || new Date().toISOString().split("T")[0],
    revision: form.revision?.value?.trim() || "Rev 00",
    priority: form.priority?.value || "Medium",
    reason_for_assessment: form.reason?.value?.trim() || "",
    status: "Draft",
  };

  try {
    const res = await fetch("/risk/assessments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json();
      alert("Error: " + (err.error || "Failed to create assessment"));
      return;
    }
    const assessment = await res.json();
    RiskState.currentAssessment = assessment;
    openAssessmentEditor(assessment);
  } catch (e) {
    alert("Network error: " + e.message);
  }
};


// ── Assessment Editor ─────────────────────────────────────────────────────────

async function openAssessment(id) {
  try {
    const [aRes, iRes] = await Promise.all([
      fetch(`/risk/assessments/${id}`),
      fetch(`/risk/assessments/${id}/items`),
    ]);
    const assessment = await aRes.json();
    const items = await iRes.json();
    RiskState.currentAssessment = assessment;
    RiskState.currentItems = items;
    openAssessmentEditor(assessment, items);
  } catch (e) {
    alert("Error loading assessment: " + e.message);
  }
}
window.openAssessment = openAssessment;

function openAssessmentEditor(assessment, items = []) {
  showRiskView("view-risk-new");
  const listView = document.getElementById("risk-list-view");
  const wizardView = document.getElementById("risk-wizard-view");
  const editorView = document.getElementById("risk-editor-view");

  if (listView) listView.style.display = "none";
  if (wizardView) wizardView.style.display = "none";
  if (editorView) {
    editorView.style.display = "block";
    renderEditor(assessment, items);
  }
}

function renderEditor(assessment, items) {
  const el = document.getElementById("risk-editor-view");
  if (!el) return;

  const methodology = assessment.methodology || "FMEA";
  const typeInfo = ASSESSMENT_TYPES[assessment.assessment_type] || { icon: "<span class=\'icon\' data-lucide=\'file-text\'></span>", label: assessment.assessment_type };
  const statusCls = (assessment.status || "Draft").toLowerCase().replace(" ", "-");
  const priorityCls = (assessment.priority || "Medium").toLowerCase();

  el.innerHTML = `
    <!-- Editor Header -->
    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px;gap:16px;flex-wrap:wrap">
      <div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
          <button class="btn-risk-secondary" onclick="backToList()" style="padding:6px 12px;font-size:12px"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
          <h2 style="font-size:18px;font-weight:800;color:var(--navy)">${typeInfo.icon} ${esc(assessment.title)}</h2>
          <span class="badge badge-${statusCls}">${assessment.status}</span>
          <span class="badge badge-${priorityCls}">${assessment.priority}</span>
        </div>
        <div style="font-size:12px;color:var(--text-muted);display:flex;gap:16px;flex-wrap:wrap">
          <span><span class=\'icon\' data-lucide=\'clipboard-list\'></span> ${esc(methodology)}</span>
          <span><span class=\'icon\' data-lucide=\'building-2\'></span> ${esc(assessment.department || "—")}</span>
          <span><span class=\'icon\' data-lucide=\'settings\'></span> ${esc(assessment.equipment || "—")}</span>
          <span><span class=\'icon\' data-lucide=\'calendar\'></span> ${esc(assessment.assessment_date || "—")}</span>
          <span><span class=\'icon\' data-lucide=\'user\'></span> ${esc(assessment.assessment_owner || "—")}</span>
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn-risk-secondary" onclick="openInfoPanel(${assessment.id})"><span class=\'icon\' data-lucide=\'pencil-line\'></span> Edit Info</button>
        <button class="btn-risk-secondary" onclick="openApprovalPanel(${assessment.id})"><span class=\'icon\' data-lucide=\'search\'></span> Review</button>
        <button class="btn-risk-secondary" onclick="generateReport(${assessment.id})"><span class=\'icon\' data-lucide=\'file-text\'></span> Report</button>
        <button class="btn-risk-secondary" onclick="exportDocx(${assessment.id})"><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span> DOCX</button>
        <button class="btn-risk-primary"   onclick="saveItems(${assessment.id})"><span class=\'icon\' data-lucide=\'save\'></span> Save</button>
      </div>
    </div>

    <!-- AI Panel -->
    <div class="risk-ai-panel" id="risk-ai-panel-${assessment.id}">
      <div class="risk-ai-panel-header">
        <span class=\'icon\' data-lucide=\'bot\'></span> AI Risk Assistant
        <span style="font-size:11px;font-weight:400;color:var(--text-muted)">Powered by Gemini 2.5 Flash</span>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <button class="btn-risk-primary" id="btn-ai-generate-${assessment.id}" onclick="aiGenerateItems(${assessment.id})">
          <span class=\'icon\' data-lucide=\'sparkles\'></span> AI Generate Risk Items
        </button>
        <button class="btn-risk-secondary" onclick="aiReview(${assessment.id})">
          <span class=\'icon\' data-lucide=\'microscope\'></span> AI Quality Review
        </button>
        <button class="btn-risk-secondary" onclick="addBlankRow()">
          ＋ Add Row
        </button>
        <span style="font-size:11px;color:var(--text-muted)">
          AI will generate ${methodology} items based on equipment and process context
        </span>
      </div>
      <div id="ai-status-${assessment.id}" style="margin-top:8px"></div>
    </div>

    <!-- Risk Items Table -->
    <div class="risk-table-container" id="risk-table-container-${assessment.id}">
      ${renderRiskTable(methodology, items, assessment.id)}
    </div>

    <!-- AI Review Results -->
    <div id="ai-review-results-${assessment.id}" style="display:none;margin-top:20px"></div>
  `;
}

function renderRiskTable(methodology, items, aid) {
  const m = methodology.toUpperCase();
  if (m === "FMEA" || m === "HAZOP" || m === "FTA" || m === "CUSTOM") {
    return renderFMEATable(items, aid);
  } else if (m === "HACCP") {
    return renderHACCPTable(items, aid);
  } else if (m === "RISK MATRIX" || m === "WHAT-IF" || m === "PHA") {
    return renderMatrixTable(items, aid);
  }
  return renderFMEATable(items, aid);
}

function renderFMEATable(items, aid) {
  const rows = items.length ? items.map((item, i) => fmeaRow(item, i)).join("") : fmeaRow({}, 0);
  return `
    <table class="risk-table" id="fmea-table-${aid}">
      <thead><tr>
        <th class="narrow">#</th>
        <th>Process Step</th>
        <th>Failure Mode</th>
        <th>Failure Effect</th>
        <th class="narrow">Sev</th>
        <th>Potential Cause</th>
        <th class="narrow">Occ</th>
        <th>Current Controls</th>
        <th class="narrow">Det</th>
        <th class="narrow">RPN</th>
        <th>Recommended Action</th>
        <th class="med">Owner</th>
        <th class="med">Due Date</th>
        <th class="med">Residual Risk</th>
        <th class="narrow">Status</th>
        <th class="narrow">Del</th>
      </tr></thead>
      <tbody id="fmea-tbody-${aid}">${rows}</tbody>
    </table>`;
}

function fmeaRow(item, i) {
  const rpnCls = getRPNClass(item.rpn);
  const rpnDisplay = item.rpn ? `<span class="rpn-cell ${rpnCls}">${item.rpn}</span>` : "";
  return `<tr data-idx="${i}">
    <td style="text-align:center;color:var(--text-muted);font-size:11px">${i + 1}</td>
    <td><input value="${esc(item.process_step || "")}" placeholder="Step / Equipment" data-field="process_step" oninput="onCellInput(this)"></td>
    <td><textarea rows="2" placeholder="Failure mode" data-field="failure_mode" oninput="onCellInput(this)">${esc(item.failure_mode || "")}</textarea></td>
    <td><textarea rows="2" placeholder="Effect on patient/product" data-field="failure_effect" oninput="onCellInput(this)">${esc(item.failure_effect || "")}</textarea></td>
    <td><input type="number" min="1" max="10" value="${item.severity || ""}" placeholder="1-10" data-field="severity" oninput="recalcRPN(this)"></td>
    <td><textarea rows="2" placeholder="Root cause" data-field="potential_cause" oninput="onCellInput(this)">${esc(item.potential_cause || "")}</textarea></td>
    <td><input type="number" min="1" max="10" value="${item.occurrence || ""}" placeholder="1-10" data-field="occurrence" oninput="recalcRPN(this)"></td>
    <td><textarea rows="2" placeholder="Current controls" data-field="current_controls" oninput="onCellInput(this)">${esc(item.current_controls || "")}</textarea></td>
    <td><input type="number" min="1" max="10" value="${item.detection || ""}" placeholder="1-10" data-field="detection" oninput="recalcRPN(this)"></td>
    <td data-field="rpn-display">${rpnDisplay}</td>
    <td><textarea rows="2" placeholder="Recommended action" data-field="recommended_action" oninput="onCellInput(this)">${esc(item.recommended_action || "")}</textarea></td>
    <td><input value="${esc(item.action_owner || "")}" placeholder="Owner" data-field="action_owner" oninput="onCellInput(this)"></td>
    <td><input type="date" value="${esc(item.due_date || "")}" data-field="due_date" oninput="onCellInput(this)"></td>
    <td>
      <select data-field="residual_risk" onchange="onCellInput(this)">
        <option value="">Select</option>
        ${["Low","Medium","High","Critical"].map(v => `<option${item.residual_risk === v ? " selected" : ""}>${v}</option>`).join("")}
      </select>
    </td>
    <td>
      <select data-field="status" onchange="onCellInput(this)">
        ${["Open","In Progress","Closed"].map(v => `<option${item.status === v ? " selected" : ""}>${v}</option>`).join("")}
      </select>
    </td>
 <td><button class="btn-risk-icon"onclick="deleteRow(this)"title="Delete row"></button></td>
  </tr>`;
}

function renderHACCPTable(items, aid) {
  const rows = items.length ? items.map((item, i) => haccpRow(item, i)).join("") : haccpRow({}, 0);
  return `
    <table class="risk-table" id="haccp-table-${aid}">
      <thead><tr>
        <th class="narrow">#</th>
        <th>Process Step</th>
        <th>Hazard</th>
        <th class="med">Category</th>
        <th>Preventive Measure</th>
        <th class="narrow">CCP?</th>
        <th>Critical Limit</th>
        <th>Monitoring</th>
        <th>Corrective Action</th>
        <th>Verification</th>
        <th>Records</th>
        <th class="narrow">Status</th>
        <th class="narrow">Del</th>
      </tr></thead>
      <tbody id="haccp-tbody-${aid}">${rows}</tbody>
    </table>`;
}

function haccpRow(item, i) {
  return `<tr data-idx="${i}">
    <td style="text-align:center;color:var(--text-muted);font-size:11px">${i + 1}</td>
    <td><input value="${esc(item.process_step || "")}" placeholder="Process step" data-field="process_step" oninput="onCellInput(this)"></td>
    <td><textarea rows="2" placeholder="Identified hazard" data-field="hazard" oninput="onCellInput(this)">${esc(item.hazard || "")}</textarea></td>
    <td>
      <select data-field="hazard_category" onchange="onCellInput(this)">
        <option value="">Type</option>
        ${["Biological","Chemical","Physical","Cross-contamination","Microbiological"].map(v => `<option${item.hazard_category === v ? " selected" : ""}>${v}</option>`).join("")}
      </select>
    </td>
    <td><textarea rows="2" placeholder="Preventive control" data-field="preventive_measure" oninput="onCellInput(this)">${esc(item.preventive_measure || "")}</textarea></td>
    <td style="text-align:center">
      <input type="checkbox" data-field="is_ccp" onchange="onCellInput(this)" ${item.is_ccp ? "checked" : ""}>
    </td>
    <td><input value="${esc(item.critical_limit || "")}" placeholder="e.g. ≥121°C / ≥15 min" data-field="critical_limit" oninput="onCellInput(this)"></td>
    <td><textarea rows="2" placeholder="Monitoring procedure" data-field="monitoring" oninput="onCellInput(this)">${esc(item.monitoring || "")}</textarea></td>
    <td><textarea rows="2" placeholder="Corrective action" data-field="corrective_action" oninput="onCellInput(this)">${esc(item.corrective_action || "")}</textarea></td>
    <td><textarea rows="2" placeholder="Verification activity" data-field="verification" oninput="onCellInput(this)">${esc(item.verification || "")}</textarea></td>
    <td><input value="${esc(item.records || "")}" placeholder="Records / documents" data-field="records" oninput="onCellInput(this)"></td>
    <td>
      <select data-field="status" onchange="onCellInput(this)">
        ${["Open","In Progress","Closed"].map(v => `<option${item.status === v ? " selected" : ""}>${v}</option>`).join("")}
      </select>
    </td>
 <td><button class="btn-risk-icon"onclick="deleteRow(this)"title="Delete"></button></td>
  </tr>`;
}

function renderMatrixTable(items, aid) {
  const rows = items.length ? items.map((item, i) => matrixRow(item, i)).join("") : matrixRow({}, 0);
  return `
    <table class="risk-table" id="matrix-table-${aid}">
      <thead><tr>
        <th class="narrow">#</th>
        <th>Process / Activity</th>
        <th>Risk Scenario</th>
        <th>Failure Effect</th>
        <th class="med">Probability</th>
        <th class="med">Impact</th>
        <th class="med">Risk Rating</th>
        <th class="med">Acceptance</th>
        <th>Current Controls</th>
        <th>Recommended Action</th>
        <th class="med">Owner</th>
        <th class="med">Residual Risk</th>
        <th class="narrow">Status</th>
        <th class="narrow">Del</th>
      </tr></thead>
      <tbody id="matrix-tbody-${aid}">${rows}</tbody>
    </table>`;
}

function matrixRow(item, i) {
  const ratingCls = getRatingClass(item.risk_rating);
  const probs = ["Rare","Unlikely","Possible","Likely","Almost Certain"];
  const impacts = ["Negligible","Minor","Moderate","Major","Catastrophic"];
  const ratings = ["Low","Medium","High","Critical"];
  const accepts = ["Acceptable","ALARP","Unacceptable"];

  return `<tr data-idx="${i}">
    <td style="text-align:center;color:var(--text-muted);font-size:11px">${i + 1}</td>
    <td><input value="${esc(item.process_step || "")}" placeholder="Activity / step" data-field="process_step" oninput="onCellInput(this)"></td>
    <td><textarea rows="2" placeholder="Risk scenario" data-field="failure_mode" oninput="onCellInput(this)">${esc(item.failure_mode || "")}</textarea></td>
    <td><textarea rows="2" placeholder="Consequence" data-field="failure_effect" oninput="onCellInput(this)">${esc(item.failure_effect || "")}</textarea></td>
    <td>
      <select data-field="probability" onchange="recalcRating(this)">
        <option value="">Select</option>
        ${probs.map(v => `<option${item.probability === v ? " selected" : ""}>${v}</option>`).join("")}
      </select>
    </td>
    <td>
      <select data-field="impact" onchange="recalcRating(this)">
        <option value="">Select</option>
        ${impacts.map(v => `<option${item.impact === v ? " selected" : ""}>${v}</option>`).join("")}
      </select>
    </td>
    <td data-field="risk-rating-display">
      <span class="rpn-cell ${ratingCls}">${item.risk_rating || "—"}</span>
    </td>
    <td>
      <select data-field="risk_acceptance" onchange="onCellInput(this)">
        <option value="">Select</option>
        ${accepts.map(v => `<option${item.risk_acceptance === v ? " selected" : ""}>${v}</option>`).join("")}
      </select>
    </td>
    <td><textarea rows="2" placeholder="Existing controls" data-field="current_controls" oninput="onCellInput(this)">${esc(item.current_controls || "")}</textarea></td>
    <td><textarea rows="2" placeholder="Mitigation action" data-field="recommended_action" oninput="onCellInput(this)">${esc(item.recommended_action || "")}</textarea></td>
    <td><input value="${esc(item.action_owner || "")}" placeholder="Owner" data-field="action_owner" oninput="onCellInput(this)"></td>
    <td>
      <select data-field="residual_risk" onchange="onCellInput(this)">
        <option value="">Select</option>
        ${ratings.map(v => `<option${item.residual_risk === v ? " selected" : ""}>${v}</option>`).join("")}
      </select>
    </td>
    <td>
      <select data-field="status" onchange="onCellInput(this)">
        ${["Open","In Progress","Closed"].map(v => `<option${item.status === v ? " selected" : ""}>${v}</option>`).join("")}
      </select>
    </td>
 <td><button class="btn-risk-icon"onclick="deleteRow(this)"title="Delete"></button></td>
  </tr>`;
}


// ── Table event handlers ───────────────────────────────────────────────────────

window.onCellInput = function (el) {
  // No-op for now — data collected on save
};

window.recalcRPN = function (el) {
  const row = el.closest("tr");
  if (!row) return;
  const s = parseInt(row.querySelector("[data-field='severity']")?.value) || 0;
  const o = parseInt(row.querySelector("[data-field='occurrence']")?.value) || 0;
  const d = parseInt(row.querySelector("[data-field='detection']")?.value) || 0;
  const rpnCell = row.querySelector("[data-field='rpn-display']");
  if (!rpnCell) return;
  if (s && o && d) {
    const rpn = s * o * d;
    const cls = getRPNClass(rpn);
    rpnCell.innerHTML = `<span class="rpn-cell ${cls}">${rpn}</span>`;
  } else {
    rpnCell.innerHTML = "";
  }
};

const PROB_MAP = { "Rare": 1, "Unlikely": 2, "Possible": 3, "Likely": 4, "Almost Certain": 5 };
const IMPACT_MAP = { "Negligible": 1, "Minor": 2, "Moderate": 3, "Major": 4, "Catastrophic": 5 };

window.recalcRating = function (el) {
  const row = el.closest("tr");
  if (!row) return;
  const pVal = row.querySelector("[data-field='probability']")?.value;
  const iVal = row.querySelector("[data-field='impact']")?.value;
  const ratingCell = row.querySelector("[data-field='risk-rating-display']");
  if (!ratingCell || !pVal || !iVal) return;
  const score = (PROB_MAP[pVal] || 0) * (IMPACT_MAP[iVal] || 0);
  let rating = "Low";
  if (score >= 15) rating = "Critical";
  else if (score >= 10) rating = "High";
  else if (score >= 5) rating = "Medium";
  const cls = getRatingClass(rating);
  ratingCell.innerHTML = `<span class="rpn-cell ${cls}">${rating}</span>`;
  // Also update hidden risk_rating field if present
  const rr = row.querySelector("[data-field='risk_rating']");
  if (rr) rr.value = rating;
};

window.deleteRow = function (btn) {
  const row = btn.closest("tr");
  if (!row) return;
  if (document.querySelectorAll("tbody tr").length <= 1) { alert("Keep at least one row."); return; }
  row.remove();
  // Renumber
  const tbody = row.closest("tbody");
  if (tbody) {
    tbody.querySelectorAll("tr").forEach((tr, i) => {
      tr.dataset.idx = i;
      const firstTd = tr.querySelector("td:first-child");
      if (firstTd) firstTd.textContent = i + 1;
    });
  }
};

window.addBlankRow = function () {
  if (!RiskState.currentAssessment) return;
  const methodology = RiskState.currentAssessment.methodology || "FMEA";
  const m = methodology.toUpperCase();
  let tbody;
  if (m === "HACCP") {
    tbody = document.getElementById(`haccp-tbody-${RiskState.currentAssessment.id}`);
    if (tbody) {
      const rows = tbody.querySelectorAll("tr").length;
      tbody.insertAdjacentHTML("beforeend", haccpRow({}, rows));
    }
  } else if (m === "RISK MATRIX" || m === "WHAT-IF") {
    tbody = document.getElementById(`matrix-tbody-${RiskState.currentAssessment.id}`);
    if (tbody) {
      const rows = tbody.querySelectorAll("tr").length;
      tbody.insertAdjacentHTML("beforeend", matrixRow({}, rows));
    }
  } else {
    tbody = document.getElementById(`fmea-tbody-${RiskState.currentAssessment.id}`);
    if (tbody) {
      const rows = tbody.querySelectorAll("tr").length;
      tbody.insertAdjacentHTML("beforeend", fmeaRow({}, rows));
    }
  }
};

function collectTableRows() {
  const methodology = RiskState.currentAssessment?.methodology || "FMEA";
  const m = methodology.toUpperCase();
  const aid = RiskState.currentAssessment?.id;
  let tbody;
  if (m === "HACCP") tbody = document.getElementById(`haccp-tbody-${aid}`);
  else if (m === "RISK MATRIX" || m === "WHAT-IF") tbody = document.getElementById(`matrix-tbody-${aid}`);
  else tbody = document.getElementById(`fmea-tbody-${aid}`);

  if (!tbody) return [];
  const rows = [];
  tbody.querySelectorAll("tr").forEach(tr => {
    const row = {};
    tr.querySelectorAll("[data-field]").forEach(el => {
      const field = el.dataset.field;
      if (field && !field.includes("-display")) {
        if (el.type === "checkbox") row[field] = el.checked ? 1 : 0;
        else row[field] = el.value;
      }
    });
    // Compute RPN
    const s = parseInt(row.severity) || 0;
    const o = parseInt(row.occurrence) || 0;
    const d = parseInt(row.detection) || 0;
    if (s && o && d) row.rpn = s * o * d;
    // Compute risk_rating from probability × impact
    if (row.probability && row.impact) {
      const score = (PROB_MAP[row.probability] || 0) * (IMPACT_MAP[row.impact] || 0);
      if (score >= 15) row.risk_rating = "Critical";
      else if (score >= 10) row.risk_rating = "High";
      else if (score >= 5) row.risk_rating = "Medium";
      else row.risk_rating = "Low";
    }
    rows.push(row);
  });
  return rows;
}

window.saveItems = async function (aid) {
  const items = collectTableRows();
  try {
    const res = await fetch(`/risk/assessments/${aid}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(items),
    });
    const saved = await res.json();
    RiskState.currentItems = saved;
 showToast(`Saved ${saved.length} risk items`);
  } catch (e) {
    alert("Error saving: " + e.message);
  }
};


// ── AI Generation ─────────────────────────────────────────────────────────────

window.aiGenerateItems = async function (aid) {
  if (RiskState.isGenerating) return;
  const a = RiskState.currentAssessment;
  if (!a) return;

  if (!confirm(`Generate AI risk items for "${a.title}" using ${a.methodology}?\n\nThis will replace any unsaved rows in the table.`)) return;

  RiskState.isGenerating = true;
  const statusEl = document.getElementById(`ai-status-${aid}`);
  const btn = document.getElementById(`btn-ai-generate-${aid}`);
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.innerHTML = `<div class="risk-ai-generating"><div class="spinner"></div> Generating ${a.methodology} risk items with AI…</div>`;

  try {
    const es = new EventSource(`/risk/assessments/${aid}/generate`);
    // POST via fetch instead
    es.close();

    const res = await fetch(`/risk/assessments/${aid}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    if (res.headers.get("content-type")?.includes("text/event-stream")) {
      // Handle SSE
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let done = false;

      while (!done) {
        const { value, done: streamDone } = await reader.read();
        done = streamDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop();
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const event = JSON.parse(line.slice(6));
                if (event.done) {
                  if (statusEl) statusEl.innerHTML = `<span style="color:var(--risk-low)"><span class=\'icon\' data-lucide=\'check-circle-2\'></span> Generated ${event.count} risk items</span>`;
                  // Reload items
                  const iRes = await fetch(`/risk/assessments/${aid}/items`);
                  const items = await iRes.json();
                  RiskState.currentItems = items;
                  const container = document.getElementById(`risk-table-container-${aid}`);
                  if (container) container.innerHTML = renderRiskTable(a.methodology, items, aid);
                }
              } catch (_) {}
            }
          }
        }
      }
    } else {
      // Fallback: non-streaming response
      const data = await res.json();
      if (statusEl) statusEl.innerHTML = `<span style="color:var(--risk-low)"><span class=\'icon\' data-lucide=\'check-circle-2\'></span> Generation complete</span>`;
      const iRes = await fetch(`/risk/assessments/${aid}/items`);
      const items = await iRes.json();
      RiskState.currentItems = items;
      const container = document.getElementById(`risk-table-container-${aid}`);
      if (container) container.innerHTML = renderRiskTable(a.methodology, items, aid);
    }
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<span style="color:var(--risk-critical)"><span class=\'icon\' data-lucide=\'circle-x\'></span> Error: ${e.message}</span>`;
  } finally {
    RiskState.isGenerating = false;
    if (btn) btn.disabled = false;
  }
};

window.aiReview = async function (aid) {
  const reviewEl = document.getElementById(`ai-review-results-${aid}`);
  if (!reviewEl) return;
  reviewEl.style.display = "block";
  reviewEl.innerHTML = `<div class="risk-section-card">
    <div class="risk-section-body">
      <div class="risk-ai-generating"><div class="spinner"></div> Running AI Quality Review…</div>
    </div>
  </div>`;

  try {
    const res = await fetch(`/risk/assessments/${aid}/review`, { method: "POST" });
    const review = await res.json();
    if (review.error) throw new Error(review.error);
    renderReviewResults(reviewEl, review);
  } catch (e) {
    reviewEl.innerHTML = `<div class="risk-section-card"><div class="risk-section-body">
      <div class="risk-empty"><p>Review failed: ${e.message}</p></div>
    </div></div>`;
  }
};

function renderReviewResults(el, r) {
  const overall = r.overall_score || 0;
  const scoreClass = overall >= 80 ? "score-excellent" : overall >= 65 ? "score-good" : overall >= 50 ? "score-fair" : "score-poor";
  const recBadge = r.recommendation === "Approve" ? "badge-approved" : r.recommendation === "Reject" ? "badge-critical" : "badge-in-review";

  el.innerHTML = `
    <div class="risk-section-card">
      <div class="risk-section-title"><span class=\'icon\' data-lucide=\'bot\'></span> AI Quality Review Results
        <span class="badge ${recBadge}" style="margin-left:auto">${r.recommendation || "Revise"}</span>
      </div>
      <div class="risk-section-body">
        <div class="review-score-grid">
          ${scoreCard(r.completeness_score, "Completeness")}
          ${scoreCard(r.regulatory_compliance_score, "Regulatory Compliance")}
          ${scoreCard(r.consistency_score, "Consistency")}
          ${scoreCard(r.overall_score, "Overall Score")}
        </div>

        ${reviewList("<span class='icon' data-lucide='circle'></span> Critical Findings", r.critical_findings, "#F7E8E7", "var(--risk-critical)")}
        ${reviewList("<span class='icon' data-lucide='alert-triangle'></span> Missing Risks", r.missing_risks, "#FFF4E5", "var(--risk-high)")}
        ${reviewList("<span class='icon' data-lucide='lightbulb'></span> Suggested Improvements", r.suggested_improvements, "#E8F2EA", "var(--risk-low)")}

        ${r.reviewer_comments ? `<div style="background:#F1ECE6;border-radius:8px;padding:14px;margin-top:12px">
          <div style="font-size:12px;font-weight:700;color:var(--navy);margin-bottom:6px"><span class=\'icon\' data-lucide=\'pencil-line\'></span> AI Reviewer Comments</div>
          <p style="font-size:13px;line-height:1.6;color:var(--text)">${esc(r.reviewer_comments)}</p>
        </div>` : ""}

        ${r.final_summary ? `<div style="background:#F1ECE6;border-radius:8px;padding:14px;margin-top:12px;border-left:4px solid var(--risk-accent)">
          <div style="font-size:12px;font-weight:700;color:var(--risk-accent);margin-bottom:6px"><span class=\'icon\' data-lucide=\'clipboard-list\'></span> Final Summary</div>
          <p style="font-size:13px;line-height:1.6;color:var(--text)">${esc(r.final_summary)}</p>
        </div>` : ""}
      </div>
    </div>
  `;
}

function scoreCard(score, label) {
  const s = score || 0;
  const cls = s >= 80 ? "score-excellent" : s >= 65 ? "score-good" : s >= 50 ? "score-fair" : "score-poor";
  return `<div class="review-score-card">
    <div class="review-score-value ${cls}">${s}</div>
    <div class="review-score-label">${label}</div>
  </div>`;
}

function reviewList(title, items, bg, color) {
  if (!items || !items.length) return "";
  return `<div style="background:${bg};border-radius:8px;padding:14px;margin-top:12px">
    <div style="font-size:12px;font-weight:700;color:${color};margin-bottom:8px">${title}</div>
    <ul style="padding-left:18px;font-size:12px;line-height:1.8;color:var(--text)">
      ${items.map(i => `<li>${esc(i)}</li>`).join("")}
    </ul>
  </div>`;
}


// ── Report & Export ───────────────────────────────────────────────────────────

window.generateReport = async function (aid) {
  showRiskView("view-risk-reports");
  const body = document.getElementById("risk-reports-body");
  if (!body) return;
  body.innerHTML = `<div class="risk-ai-generating"><div class="spinner"></div> Generating report…</div>`;

  try {
    const res = await fetch(`/risk/assessments/${aid}/report`);
    const data = await res.json();
    body.innerHTML = `
      <div style="display:flex;gap:12px;margin-bottom:16px">
        <button class="btn-risk-primary" onclick="exportDocx(${aid})"><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span> Export DOCX</button>
        <button class="btn-risk-secondary" onclick="printReport()"><span class=\'icon\' data-lucide=\'printer\'></span> Print</button>
      </div>
      <div style="background:#FFF;border-radius:12px;border:1px solid var(--risk-border);padding:32px;max-width:1000px;box-shadow:var(--shadow)" id="report-content">
        ${marked.parse ? marked.parse(data.markdown) : data.markdown}
      </div>`;
  } catch (e) {
    body.innerHTML = `<div class="risk-empty"><p>Report generation failed: ${e.message}</p></div>`;
  }
};

window.exportDocx = async function (aid) {
  try {
    const res = await fetch(`/risk/assessments/${aid}/export/docx`, { method: "POST" });
    if (!res.ok) { alert("Export failed"); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `RiskAssessment_${aid}.docx`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("Export error: " + e.message);
  }
};

window.printReport = function () {
  const content = document.getElementById("report-content");
  if (!content) return;
  const win = window.open("", "_blank");
  win.document.write(`<html><head><title>Risk Assessment Report</title>
    <style>body{font-family:serif;padding:40px;max-width:900px;margin:0 auto}
    table{border-collapse:collapse;width:100%} th,td{border:1px solid #E6DED6;padding:6px;font-size:11px}
    th{background:#5B4C43;color:#FFF} h1,h2,h3{color:#5B4C43}</style>
    </head><body>${content.innerHTML}</body></html>`);
  win.document.close();
  win.print();
};


// ── Approval ──────────────────────────────────────────────────────────────────

window.openApprovalPanel = async function (aid) {
  showRiskView("view-risk-approval");
  const body = document.getElementById("risk-approval-body");
  if (!body) return;
  body.innerHTML = `<div class="risk-ai-generating"><div class="spinner"></div></div>`;

  try {
    const [aRes, trailRes] = await Promise.all([
      fetch(`/risk/assessments/${aid}`),
      fetch(`/risk/assessments/${aid}/approval`),
    ]);
    const assessment = await aRes.json();
    const trail = await trailRes.json();
    riskRenderApprovalPanel(body, assessment, trail);
  } catch (e) {
    body.innerHTML = `<div class="risk-empty"><p>Error: ${e.message}</p></div>`;
  }
};

function riskRenderApprovalPanel(body, a, trail) {
  const statusCls = (a.status || "Draft").toLowerCase().replace(" ", "-");
  body.innerHTML = `
    <div style="max-width:800px">
      <div class="risk-section-card" style="margin-bottom:20px">
        <div class="risk-section-title"><span class=\'icon\' data-lucide=\'clipboard-list\'></span> Assessment Details</div>
        <div class="risk-section-body" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:13px">
          <div><strong>Title:</strong> ${esc(a.title)}</div>
          <div><strong>Status:</strong> <span class="badge badge-${statusCls}">${a.status}</span></div>
          <div><strong>Type:</strong> ${esc(a.assessment_type)}</div>
          <div><strong>Methodology:</strong> ${esc(a.methodology)}</div>
          <div><strong>Owner:</strong> ${esc(a.assessment_owner || "—")}</div>
          <div><strong>Reviewer:</strong> ${esc(a.reviewer || "—")}</div>
          <div><strong>Approver:</strong> ${esc(a.approver || "—")}</div>
          <div><strong>Revision:</strong> ${esc(a.revision || "—")}</div>
        </div>
      </div>

      <div class="risk-section-card" style="margin-bottom:20px">
        <div class="risk-section-title"><span class=\'icon\' data-lucide=\'repeat\'></span> Workflow Actions</div>
        <div class="risk-section-body">
          <div class="form-grid" style="margin-bottom:16px">
            <div class="form-field">
              <label>Action</label>
              <select id="approval-action">
                <option value="">Select action</option>
                <option>Submitted for Review</option>
                <option>Reviewed</option>
                <option>Approved</option>
                <option>Rejected</option>
                <option>Closed</option>
              </select>
            </div>
            <div class="form-field">
              <label>Performed By</label>
              <input id="approval-by" placeholder="Your name" value="${esc(a.assessment_owner || "")}">
            </div>
            <div class="form-field">
              <label>Role</label>
              <select id="approval-role">
                <option>Owner</option><option>Reviewer</option><option>Approver</option>
                <option>Quality Manager</option><option>QA Head</option>
              </select>
            </div>
            <div class="form-field span-2">
              <label>Comments</label>
              <textarea id="approval-comments" rows="3" placeholder="Review / approval comments"></textarea>
            </div>
          </div>
          <button class="btn-risk-primary" onclick="submitApproval(${a.id})">Submit Action</button>
        </div>
      </div>

      <div class="risk-section-card">
        <div class="risk-section-title"><span class=\'icon\' data-lucide=\'scroll-text\'></span> Approval Trail</div>
        <div class="risk-section-body">
          ${trail.length ? `<div class="approval-timeline">${trail.map(e => approvalEntryHtml(e)).join("")}</div>` :
            `<div class="risk-empty"><p>No approval entries yet.</p></div>`}
        </div>
      </div>
    </div>`;
}

function approvalEntryHtml(e) {
  return `<div class="approval-entry">
    <div class="approval-entry-header">
      <span class="approval-action">${esc(e.action)}</span>
      <span class="approval-meta">by ${esc(e.performed_by || "System")} (${esc(e.role || "")}) · ${esc(e.timestamp?.replace("T"," ").split(".")[0] || "")}</span>
    </div>
    ${e.comments ? `<div class="approval-comments">"${esc(e.comments)}"</div>` : ""}
  </div>`;
}

window.submitApproval = async function (aid) {
  const action = document.getElementById("approval-action")?.value;
  if (!action) { alert("Select an action."); return; }
  const by = document.getElementById("approval-by")?.value || "";
  const role = document.getElementById("approval-role")?.value || "";
  const comments = document.getElementById("approval-comments")?.value || "";

  try {
    const res = await fetch(`/risk/assessments/${aid}/approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, performed_by: by, role, comments }),
    });
    if (!res.ok) throw new Error((await res.json()).error);
 showToast(`${action} recorded`);
    openApprovalPanel(aid);
  } catch (e) {
    alert("Error: " + e.message);
  }
};


// ── Risk Library ──────────────────────────────────────────────────────────────

async function loadLibrary() {
  showRiskView("view-risk-library");
  const body = document.getElementById("risk-library-body");
  if (!body) return;
  body.innerHTML = `<div class="risk-ai-generating"><div class="spinner"></div> Loading library…</div>`;

  try {
    const res = await fetch("/risk/library");
    const entries = await res.json();
    renderLibrary(entries);
  } catch (e) {
    body.innerHTML = `<div class="risk-empty"><p>Error: ${e.message}</p></div>`;
  }
}
window.loadLibrary = loadLibrary;

function renderLibrary(entries) {
  const body = document.getElementById("risk-library-body");
  if (!entries.length) {
    body.innerHTML = `<div class="risk-empty">
      <div class="risk-empty-icon"><span class=\'icon\' data-lucide=\'book-open\'></span></div>
      <h3>Library is empty</h3>
      <p>Approve assessments to automatically populate the risk library.</p>
    </div>`;
    return;
  }
  body.innerHTML = `
    <div class="library-filters">
      <select id="lib-filter-cat" onchange="filterLibrary()">
        ${LIBRARY_CATEGORIES.map(c => `<option>${c}</option>`).join("")}
      </select>
      <input id="lib-search" placeholder="Search failure modes…" oninput="filterLibrary()">
    </div>
    <div class="risk-table-container">
      <table class="risk-table" id="library-table">
        <thead><tr>
          <th>#</th><th>Category</th><th>Failure Mode / Hazard</th>
          <th>Effect</th><th>Cause</th><th>Controls</th>
          <th class="narrow">Sev</th><th class="narrow">Occ</th>
          <th class="narrow">Det</th><th class="narrow">RPN</th>
          <th>Reg. Ref.</th>
        </tr></thead>
        <tbody id="library-tbody">
          ${entries.map((e, i) => `
            <tr>
              <td style="text-align:center;color:var(--text-muted);font-size:11px">${i+1}</td>
              <td><span class="badge badge-in-review">${esc(e.category)}</span></td>
              <td style="font-weight:600">${esc(e.failure_mode || "—")}</td>
              <td>${esc(e.failure_effect || "—")}</td>
              <td>${esc(e.potential_cause || "—")}</td>
              <td>${esc(e.current_controls || "—")}</td>
              <td style="text-align:center">${e.typical_severity ?? "—"}</td>
              <td style="text-align:center">${e.typical_occurrence ?? "—"}</td>
              <td style="text-align:center">${e.typical_detection ?? "—"}</td>
              <td style="text-align:center">${e.typical_rpn ? `<span class="rpn-cell ${getRPNClass(e.typical_rpn)}">${e.typical_rpn}</span>` : "—"}</td>
              <td style="font-size:11px">${esc(e.regulatory_reference || "—")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>`;
}

window.filterLibrary = async function () {
  const cat = document.getElementById("lib-filter-cat")?.value;
  const q = document.getElementById("lib-search")?.value;
  const params = new URLSearchParams();
  if (cat && cat !== "All") params.append("category", cat);
  if (q) params.append("q", q);
  const res = await fetch(`/risk/library?${params}`);
  const entries = await res.json();
  renderLibrary(entries);
};


// ── Templates ─────────────────────────────────────────────────────────────────

function loadTemplates() {
  showRiskView("view-risk-templates");
  const body = document.getElementById("risk-templates-body");
  if (!body) return;
  body.innerHTML = `
    <div class="template-grid">
      ${TEMPLATES.map(t => `
        <div class="template-card" onclick="useTemplate(${JSON.stringify(t).replace(/"/g, '&quot;')})">
          <div class="template-card-icon">${t.icon}</div>
          <div class="template-card-name">${t.name}</div>
          <div class="template-card-desc">${t.sub}</div>
          <div class="template-card-meta">
            <span class="badge badge-in-review" style="font-size:10px">${t.type}</span>
            <span class="badge badge-draft" style="font-size:10px">${t.method}</span>
          </div>
        </div>
      `).join("")}
    </div>`;
}
window.loadTemplates = loadTemplates;

window.useTemplate = async function (t) {
  const title = prompt(`Create assessment from template: "${t.name}"\n\nEnter assessment title:`, t.name);
  if (!title) return;

  const today = new Date().toISOString().split("T")[0];
  const data = {
    title,
    assessment_type: t.type,
    assessment_subtype: t.sub,
    methodology: t.method,
    department: t.dept,
    status: "Draft",
    priority: "Medium",
    revision: "Rev 00",
    assessment_date: today,
    reason_for_assessment: `Risk assessment based on template: ${t.name}`,
  };

  try {
    const res = await fetch("/risk/assessments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const assessment = await res.json();
    RiskState.currentAssessment = assessment;
    openAssessmentEditor(assessment, []);
 showToast(`Assessment created from template: ${t.name}`);
  } catch (e) {
    alert("Error: " + e.message);
  }
};


// ── AI Assistant ──────────────────────────────────────────────────────────────

function loadAIAssistant() {
  showRiskView("view-risk-assistant");
  const body = document.getElementById("risk-assistant-body");
  if (!body) return;
  body.innerHTML = `
    <div class="risk-ai-panel" style="max-width:800px">
      <div class="risk-ai-panel-header"><span class=\'icon\' data-lucide=\'bot\'></span> AI Risk Assistant</div>
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px">
        Ask the AI Risk Assistant any question about pharmaceutical risk management,
        ICH Q9 methodology, FMEA scoring, HACCP principles, or regulatory requirements.
      </p>
      <div id="ai-assistant-messages" style="min-height:200px;margin-bottom:16px"></div>
      <div style="display:flex;gap:10px">
        <input id="ai-assistant-input" placeholder="Ask about risk management, ICH Q9, FMEA, HACCP…"
               style="flex:1;padding:10px 14px;border:1.5px solid var(--risk-border);border-radius:8px;font-family:inherit;font-size:13px;outline:none"
               onkeydown="if(event.key==='Enter')sendAIQuestion()">
        <button class="btn-risk-primary" onclick="sendAIQuestion()">Send</button>
      </div>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        ${[
          "What is ICH Q9?",
          "How to calculate RPN?",
          "What is HACCP?",
          "When to use HAZOP?",
          "What is risk acceptability criteria?",
          "How to reduce RPN?",
        ].map(q => `<button class="btn-risk-secondary" style="font-size:11px;padding:5px 10px"
                    onclick="document.getElementById('ai-assistant-input').value=this.textContent;sendAIQuestion()">${q}</button>`).join("")}
      </div>
    </div>`;
}
window.loadAIAssistant = loadAIAssistant;

window.sendAIQuestion = async function () {
  const input = document.getElementById("ai-assistant-input");
  const msgs = document.getElementById("ai-assistant-messages");
  if (!input || !msgs) return;
  const q = input.value.trim();
  if (!q) return;
  input.value = "";

  msgs.insertAdjacentHTML("beforeend", `
    <div style="background:#F1ECE6;border-radius:8px;padding:10px 14px;margin-bottom:10px;font-size:13px">
      <strong>You:</strong> ${esc(q)}
    </div>`);

  const aiEl = document.createElement("div");
  aiEl.style.cssText = "background:#F1ECE6;border-radius:8px;padding:10px 14px;margin-bottom:10px;font-size:13px;border-left:3px solid var(--risk-accent)";
  aiEl.innerHTML = `<strong>AI:</strong> <span class="risk-ai-generating"><span class="spinner" style="width:14px;height:14px;border-width:1px"></span></span>`;
  msgs.appendChild(aiEl);
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const res = await fetch("/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: `[Risk Management Query] ${q}\n\nPlease provide expert guidance on pharmaceutical quality risk management, ICH Q9 principles, and GMP compliance.`,
        use_documents: false,
      }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let answer = "";
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.token) { answer += ev.token; }
            else if (ev.done) { break; }
          } catch (_) {}
        }
      }
      aiEl.innerHTML = `<strong>AI:</strong> ${marked.parse ? marked.parse(answer) : answer}`;
      msgs.scrollTop = msgs.scrollHeight;
    }
  } catch (e) {
    aiEl.innerHTML = `<strong>AI:</strong> Error: ${e.message}`;
  }
};


// ── Navigation helpers ────────────────────────────────────────────────────────

window.backToList = function () {
  const listView = document.getElementById("risk-list-view");
  const wizardView = document.getElementById("risk-wizard-view");
  const editorView = document.getElementById("risk-editor-view");
  if (wizardView) wizardView.style.display = "none";
  if (editorView) editorView.style.display = "none";
  if (listView) listView.style.display = "block";
  loadAssessmentList();
};

function openInfoPanel(aid) {
  // Placeholder — could open a modal with editable info form
  alert("Info editing coming soon. Use the main assessment form.");
}


// ── Utility ───────────────────────────────────────────────────────────────────

function esc(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function getRPNClass(rpn) {
  if (!rpn) return "";
  if (rpn >= 200) return "rpn-critical";
  if (rpn >= 100) return "rpn-high";
  if (rpn >= 50)  return "rpn-medium";
  return "rpn-low";
}

function getRatingClass(rating) {
  if (!rating) return "";
  const r = rating.toLowerCase();
  if (r === "critical") return "rpn-critical";
  if (r === "high")     return "rpn-high";
  if (r === "medium")   return "rpn-medium";
  return "rpn-low";
}

function showToast(msg) {
  const toast = document.createElement("div");
  toast.style.cssText = `position:fixed;bottom:24px;right:24px;background:var(--navy);color:#FFF;
    padding:12px 20px;border-radius:10px;font-size:13px;z-index:9999;
    box-shadow:0 4px 20px rgba(63,58,54,0.3);animation:fadeInUp 0.3s ease`;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// Add fadeInUp animation
const style = document.createElement("style");
style.textContent = `@keyframes fadeInUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}`;
document.head.appendChild(style);
