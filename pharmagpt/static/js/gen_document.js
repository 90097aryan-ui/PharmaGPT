/**
 * gen_document.js — PharmaGPT v0.9 AI Document Generator
 *
 * 6-step wizard:
 *   1. Project Selection
 *   2. Document Type
 *   3. Equipment Information
 *   4. Dynamic Questionnaire
 *   5. Review Inputs
 *   6. Generate Draft  (structured JSON — AI call deferred to v1.0)
 *
 * Depends on: validation_config.js (VALIDATION_DOCS, VALIDATION_DOC_ORDER)
 */

// ── State ──────────────────────────────────────────────────────────────────────
let gdStep      = 1;
let gdProject   = null;   // selected project object
let gdDocType   = null;   // e.g. "IQ"
let gdEquipment = {};     // Step 3 fields
let gdAnswers   = {};     // Step 4 questionnaire answers
let gdDraft     = null;   // Final JSON draft object

let gdGeneratedContent = null;   // AI-generated markdown (once generation completes)
let gdIsGenerating     = false;
let gdGenAbort         = false;  // set true to stop rendering a stale in-flight stream

// ── Entry point ────────────────────────────────────────────────────────────────
function openGenDocument() {
  if (window.Workspace) window.Workspace.enter();

  gdStep      = 1;
  gdProject   = window.activeProject || null;
  gdDocType   = null;
  gdEquipment = {};
  gdAnswers   = {};
  gdDraft     = null;

  gdGeneratedContent = null;
  gdIsGenerating     = false;
  gdGenAbort         = false;

  _gdUpdateHeader();
  _gdRenderStep(1);
}

function _gdUpdateHeader() {
  const docs = window.VALIDATION_DOCS || {};
  const tag  = document.getElementById("gd-project-tag");
  const dtag = document.getElementById("gd-doctype-tag");
  if (tag) {
    tag.textContent = gdProject ? gdProject.name : "No project selected";
    tag.classList.toggle("is-empty", !gdProject);
  }
  if (dtag) {
    const cfg = docs[gdDocType];
    dtag.textContent = cfg ? cfg.label || gdDocType : "No document type selected";
    dtag.classList.toggle("is-empty", !gdDocType);
  }
}

const GD_STEP_LABELS = {
  1: "Project", 2: "Doc Type", 3: "Equipment",
  4: "Questions", 5: "Review", 6: "Generate",
};
const GD_STEP_ORDER = ["Project", "Doc Type", "Equipment", "Questions", "Review", "Generate"];

function _gdUpdateBreadcrumb() {
  if (!window.Workspace) return;
  const projCrumb = gdProject ? gdProject.name : "No project selected";
  const stepCrumb = GD_STEP_LABELS[gdStep] || "";
  window.Workspace.renderBreadcrumb("gd-breadcrumb", [
    { label: "Dashboard" },
    { label: projCrumb },
    { label: "Generate Document" },
    { label: `Step ${gdStep} — ${stepCrumb}`, current: true },
  ]);
}

// ── Step rendering ─────────────────────────────────────────────────────────────
function _gdRenderStep(n) {
  gdStep = n;
  _gdUpdateProgress(n);
  _gdUpdateBreadcrumb();

  for (let i = 1; i <= 6; i++) {
    const p = document.getElementById(`gd-panel-${i}`);
    if (p) p.style.display = "none";
  }
  const panel = document.getElementById(`gd-panel-${n}`);
  if (!panel) return;
  panel.style.display = "flex";

  if (n === 1) _gdStep1(panel);
  if (n === 2) _gdStep2(panel);
  if (n === 3) _gdStep3(panel);
  if (n === 4) _gdStep4(panel);
  if (n === 5) _gdStep5(panel);
  if (n === 6) _gdStep6(panel);
}

function _gdUpdateProgress(active) {
  if (window.Workspace) window.Workspace.renderProgress("gd-progress", GD_STEP_ORDER, active);
}

// ── Step 1: Project Selection ──────────────────────────────────────────────────
async function _gdStep1(panel) {
  panel.innerHTML = `
    <div class="gd-step-content">
      <h3 class="gd-step-title">Step 1 — Project Selection</h3>
      <p class="gd-step-sub">Select the project this document belongs to. The active project is pre-selected.</p>
      <div id="gd-proj-list" class="gd-proj-list"><div class="gd-loading">Loading projects…</div></div>
      <div class="gd-nav-row">
        <span></span>
        <button class="gd-btn-primary" onclick="gdNext()">Next <span class=\'icon\' data-lucide=\'arrow-right\'></span> Document Type</button>
      </div>
    </div>`;

  try {
    const res      = await fetch("/projects");
    const projects = await res.json();
    const list     = document.getElementById("gd-proj-list");

    if (!projects.length) {
      list.innerHTML = `<div class="gd-empty-note">No projects found. Create a project first using the sidebar.</div>`;
      return;
    }

    list.innerHTML = projects.map(p => {
      const sel = gdProject && gdProject.id === p.id;
      return `
        <div class="gd-proj-card ${sel ? "selected" : ""}" data-id="${p.id}" onclick="gdSelectProject(${p.id}, this)">
          <div class="gd-proj-card-left">
            <div class="gd-proj-icon"><span class=\'icon\' data-lucide=\'folder\'></span></div>
            <div>
              <div class="gd-proj-name">${_gdEsc(p.name)}</div>
              <div class="gd-proj-meta">${_gdEsc(p.equipment_name || "")}${p.department ? " · " + _gdEsc(p.department) : ""}</div>
            </div>
          </div>
          ${sel ? '<span class="gd-sel-badge"><span class=\'icon\' data-lucide=\'check\'></span> Selected</span>' : ""}
        </div>`;
    }).join("");

  } catch {
    document.getElementById("gd-proj-list").innerHTML = `<div class="gd-empty-note">Could not load projects.</div>`;
  }
}

function gdSelectProject(id, el) {
  document.querySelectorAll(".gd-proj-card").forEach(c => {
    c.classList.remove("selected");
    const badge = c.querySelector(".gd-sel-badge");
    if (badge) badge.remove();
  });
  el.classList.add("selected");
  el.insertAdjacentHTML("beforeend", `<span class="gd-sel-badge"><span class=\'icon\' data-lucide=\'check\'></span> Selected</span>`);

  // Find from window projects cache or build minimal object
  gdProject = { id, name: el.querySelector(".gd-proj-name")?.textContent || "" };
  _gdUpdateHeader();
  _gdUpdateBreadcrumb();
}

// ── Step 2: Document Type ──────────────────────────────────────────────────────
function _gdStep2(panel) {
  const order = window.VALIDATION_DOC_ORDER || [];
  const docs  = window.VALIDATION_DOCS     || {};

  panel.innerHTML = `
    <div class="gd-step-content">
      <h3 class="gd-step-title">Step 2 — Document Type</h3>
      <p class="gd-step-sub">Select the type of document you want to generate.</p>
      <div class="gd-doctype-grid">
        ${order.map(type => {
          const cfg = docs[type] || {};
          const sel = gdDocType === type;
          return `
            <div class="gd-doctype-card ${sel ? "selected" : ""}" data-type="${type}"
                 onclick="gdSelectDocType('${type}', this)"
                 style="${sel ? `border-color:${cfg.color};box-shadow:0 0 0 3px ${cfg.color}22` : ""}">
              <div class="gd-doctype-icon">${cfg.icon || "<span class=\'icon\' data-lucide=\'file-text\'></span>"}</div>
              <div class="gd-doctype-short" style="color:${cfg.color || "#8A6B52"}">${type}</div>
              <div class="gd-doctype-label">${cfg.label || type}</div>
            </div>`;
        }).join("")}
      </div>
      <div class="gd-nav-row">
        <button class="gd-btn-secondary" onclick="gdBack()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
        <button class="gd-btn-primary" onclick="gdNext()">Next <span class=\'icon\' data-lucide=\'arrow-right\'></span> Equipment Info</button>
      </div>
    </div>`;
}

function gdSelectDocType(type, el) {
  const docs = window.VALIDATION_DOCS || {};
  document.querySelectorAll(".gd-doctype-card").forEach(c => {
    c.classList.remove("selected");
    c.style.borderColor = "";
    c.style.boxShadow = "";
  });
  el.classList.add("selected");
  const cfg = docs[type] || {};
  el.style.borderColor = cfg.color || "#8A6B52";
  el.style.boxShadow  = `0 0 0 3px ${cfg.color || "#8A6B52"}22`;
  gdDocType = type;
  _gdUpdateHeader();
}

// ── Step 3: Equipment Information ─────────────────────────────────────────────
function _gdStep3(panel) {
  const proj = gdProject || window.activeProject || {};
  const eq   = gdEquipment;

  const fields = [
    { id: "equipment_name",   label: "Equipment Name",    placeholder: "e.g. HPLC System",               required: true,  value: eq.equipment_name   || proj.equipment_name  || "" },
    { id: "equipment_id",     label: "Equipment ID",      placeholder: "e.g. EQ-0042",                   required: false, value: eq.equipment_id     || "" },
    { id: "manufacturer",     label: "Manufacturer",      placeholder: "e.g. Agilent Technologies",      required: false, value: eq.manufacturer     || proj.manufacturer    || "" },
    { id: "model",            label: "Model",             placeholder: "e.g. 1260 Infinity II",          required: false, value: eq.model            || "" },
    { id: "serial_number",    label: "Serial Number",     placeholder: "e.g. DE12345678",                required: false, value: eq.serial_number    || "" },
    { id: "department",       label: "Department",        placeholder: "e.g. Quality Control",           required: false, value: eq.department       || proj.department      || "" },
    { id: "location",         label: "Location",          placeholder: "e.g. Building A, Room 204",      required: false, value: eq.location         || "" },
    { id: "product",          label: "Product",           placeholder: "e.g. Paracetamol 500 mg Tablets",required: false, value: eq.product          || "" },
    { id: "software_version", label: "Software Version",  placeholder: "e.g. v3.2.1",                    required: false, value: eq.software_version || "" },
    { id: "plc_hmi",          label: "PLC / HMI",         placeholder: "e.g. Siemens S7-300",            required: false, value: eq.plc_hmi          || "" },
    { id: "validation_type",  label: "Validation Type",   placeholder: "",                               required: false, value: eq.validation_type  || proj.validation_type || "", type: "select" },
  ];

  const valTypes = ["", "IQ", "OQ", "PQ", "IQ/OQ", "IQ/OQ/PQ", "DQ", "FAT", "SAT",
                    "CSV", "Process Validation", "Cleaning Validation", "FMEA", "CAPA", "Other"];

  const renderField = f => {
    if (f.type === "select") {
      return `
        <div class="gd-form-group">
          <label class="gd-label">${f.label}</label>
          <select class="gd-input" id="geq-${f.id}">
            ${valTypes.map(v => `<option value="${v}" ${f.value === v ? "selected" : ""}>${v || "— Select —"}</option>`).join("")}
          </select>
        </div>`;
    }
    return `
      <div class="gd-form-group">
        <label class="gd-label">${f.label}${f.required ? " *" : ""}</label>
        <input class="gd-input" id="geq-${f.id}" placeholder="${_gdEscAttr(f.placeholder)}" value="${_gdEscAttr(f.value)}" />
      </div>`;
  };

  panel.innerHTML = `
    <div class="gd-step-content">
      <h3 class="gd-step-title">Step 3 — Equipment Information</h3>
      <p class="gd-step-sub">Enter the equipment details that will appear in the document header and test sections.</p>
      <div class="gd-form-grid">
        ${fields.map(renderField).join("")}
      </div>
      <div class="gd-nav-row">
        <button class="gd-btn-secondary" onclick="gdBack()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
        <button class="gd-btn-primary" onclick="gdNext()">Next <span class=\'icon\' data-lucide=\'arrow-right\'></span> Questionnaire</button>
      </div>
    </div>`;
}

function _gdCollectEquipment() {
  const ids = ["equipment_name","equipment_id","manufacturer","model","serial_number",
                "department","location","product","software_version","plc_hmi","validation_type"];
  ids.forEach(id => {
    const el = document.getElementById(`geq-${id}`);
    if (el) gdEquipment[id] = el.value.trim();
  });
}

// ── Step 4: Dynamic Questionnaire ─────────────────────────────────────────────

const GD_QUESTIONS = {
  URS: [
    { id: "functional_requirements",    label: "Functional Requirements",         type: "textarea", placeholder: "List the key functional requirements the system must meet…" },
    { id: "performance_requirements",   label: "Performance / Capacity Requirements", type: "textarea", placeholder: "e.g. throughput, cycle time, accuracy, precision…" },
    { id: "regulatory_requirements",    label: "Regulatory / Compliance Requirements", type: "textarea", placeholder: "Applicable GMP guidelines, standards (21 CFR Part 11, EU GMP Annex 11)…" },
    { id: "interfaces",                 label: "System Interfaces",               type: "textarea", placeholder: "Interfaces with other systems, networks, utilities…" },
    { id: "environment",                label: "Environmental Conditions",         type: "text",     placeholder: "Temperature, humidity, cleanliness class…" },
    { id: "safety_requirements",        label: "Safety Requirements",              type: "textarea", placeholder: "Operator safety, containment, alarms…" },
  ],
  DQ: [
    { id: "vendor_selection_criteria",  label: "Vendor Selection Criteria",        type: "textarea", placeholder: "Criteria used to select vendor/supplier…" },
    { id: "design_specifications",      label: "Design Specifications",            type: "textarea", placeholder: "Key design parameters, materials of construction…" },
    { id: "compliance_standards",       label: "Applicable Standards",             type: "text",     placeholder: "e.g. ASME BPE, ISO 14644, GAMP 5…" },
    { id: "drawings_review",            label: "Drawings / P&ID Review Status",    type: "text",     placeholder: "e.g. Approved, Under Review…" },
    { id: "fat_requirements",           label: "FAT Requirements",                 type: "textarea", placeholder: "Tests to be conducted at vendor premises…" },
    { id: "risk_assessment_ref",        label: "Risk Assessment Reference",        type: "text",     placeholder: "e.g. FMEA-001" },
  ],
  FAT: [
    { id: "test_environment",           label: "Test Environment",                 type: "text",     placeholder: "Manufacturer's facility, address…" },
    { id: "fat_attendees",              label: "FAT Attendees",                    type: "text",     placeholder: "Names / roles of personnel witnessing FAT…" },
    { id: "test_procedures",            label: "Test Procedures / Scope",          type: "textarea", placeholder: "List the main tests / checks to be performed at FAT…" },
    { id: "acceptance_criteria",        label: "Acceptance Criteria",              type: "textarea", placeholder: "Pass / fail criteria for FAT tests…" },
    { id: "test_equipment_used",        label: "Test Equipment Used",              type: "textarea", placeholder: "Calibrated instruments / tools used during FAT…" },
    { id: "open_points_process",        label: "Open Points / Punch List Process", type: "text",     placeholder: "How open items will be tracked and resolved…" },
  ],
  SAT: [
    { id: "site_preparation",           label: "Site Preparation Status",          type: "textarea", placeholder: "Utilities available, civil works complete, area classification…" },
    { id: "utility_requirements",       label: "Utility Requirements",             type: "textarea", placeholder: "Power, water, compressed air, HVAC requirements…" },
    { id: "installation_verification",  label: "Installation Verification Scope",  type: "textarea", placeholder: "Physical checks to verify correct installation at site…" },
    { id: "fat_reference",              label: "FAT Report Reference",             type: "text",     placeholder: "e.g. FAT-001 (dated DD-Mon-YYYY)" },
    { id: "sat_attendees",              label: "SAT Attendees",                    type: "text",     placeholder: "Names / roles of personnel witnessing SAT…" },
    { id: "acceptance_criteria",        label: "Acceptance Criteria",              type: "textarea", placeholder: "Pass / fail criteria for SAT tests…" },
  ],
  IQ: [
    { id: "installation_checklist",     label: "Installation Checklist Items",     type: "textarea", placeholder: "Physical installation checks: levelling, anchoring, utility connections…" },
    { id: "documentation_received",     label: "Documentation Received",           type: "textarea", placeholder: "Manuals, drawings, FAT report, certificates of compliance…" },
    { id: "calibration_status",         label: "Calibration Status of Instruments",type: "textarea", placeholder: "List instruments and their calibration certificate numbers / due dates…" },
    { id: "spare_parts",                label: "Spare Parts / Consumables Received",type: "text",     placeholder: "List critical spare parts supplied with equipment…" },
    { id: "utility_connections",        label: "Utility Connection Verification",   type: "textarea", placeholder: "Electrical, pneumatic, water connections verified…" },
    { id: "safety_checks",              label: "Safety Checks",                    type: "textarea", placeholder: "Earthing / grounding, safety interlocks, emergency stops…" },
  ],
  OQ: [
    { id: "operating_parameters",       label: "Operating Parameters to Challenge", type: "textarea", placeholder: "Parameters and their operating ranges (e.g. temperature: 2–8 °C)…" },
    { id: "test_cases",                 label: "Test Cases / Test Scripts",         type: "textarea", placeholder: "List of OQ test cases with test IDs…" },
    { id: "challenge_tests",            label: "Worst-Case / Challenge Tests",      type: "textarea", placeholder: "Tests at upper and lower limits of operating ranges…" },
    { id: "alarm_interlock_tests",      label: "Alarm & Interlock Tests",           type: "textarea", placeholder: "Alarms, safety interlocks and emergency shutdowns to test…" },
    { id: "acceptance_criteria",        label: "Acceptance Criteria",               type: "textarea", placeholder: "Pass / fail limits for each test…" },
    { id: "iq_reference",               label: "IQ Protocol Reference",             type: "text",     placeholder: "e.g. IQ-001" },
  ],
  PQ: [
    { id: "process_parameters",         label: "Process Parameters",               type: "textarea", placeholder: "Critical process parameters and their validated ranges…" },
    { id: "number_of_runs",             label: "Number of PQ Runs",                type: "text",     placeholder: "e.g. 3 consecutive batches" },
    { id: "batch_details",              label: "Batch / Lot Details",              type: "textarea", placeholder: "Batch size, product name, lot numbers used in PQ…" },
    { id: "sampling_plan",              label: "Sampling Plan",                    type: "textarea", placeholder: "Sampling locations, frequency, sample size…" },
    { id: "acceptance_criteria",        label: "Acceptance Criteria",              type: "textarea", placeholder: "Specification limits for product quality attributes…" },
    { id: "oq_reference",               label: "OQ Protocol Reference",            type: "text",     placeholder: "e.g. OQ-001" },
  ],
  FMEA: [
    { id: "process_steps",              label: "Process / System Steps",           type: "textarea", placeholder: "List the process steps or system functions to be analysed…" },
    { id: "failure_modes",              label: "Potential Failure Modes",          type: "textarea", placeholder: "What could go wrong at each step…" },
    { id: "effects",                    label: "Effects of Failure",               type: "textarea", placeholder: "Impact on product quality, safety, compliance…" },
    { id: "causes",                     label: "Root Causes",                      type: "textarea", placeholder: "Why might each failure mode occur…" },
    { id: "current_controls",           label: "Current Controls",                 type: "textarea", placeholder: "Existing prevention / detection controls…" },
    { id: "rpn_threshold",              label: "RPN Threshold for Action",         type: "text",     placeholder: "e.g. RPN ≥ 100 requires corrective action" },
  ],
  CAPA: [
    { id: "root_cause_method",          label: "Root Cause Analysis Method",       type: "text",     placeholder: "e.g. Fishbone, 5-Why, Fault Tree…" },
    { id: "root_cause_finding",         label: "Root Cause Finding",               type: "textarea", placeholder: "Describe the identified root cause…" },
    { id: "immediate_actions",          label: "Immediate / Containment Actions",  type: "textarea", placeholder: "Actions taken immediately to contain the problem…" },
    { id: "corrective_actions",         label: "Corrective Actions",               type: "textarea", placeholder: "Actions to eliminate the root cause…" },
    { id: "preventive_actions",         label: "Preventive Actions",               type: "textarea", placeholder: "Actions to prevent recurrence in similar processes…" },
    { id: "effectiveness_check",        label: "Effectiveness Check Plan",         type: "textarea", placeholder: "How and when effectiveness will be verified…" },
  ],
  Deviation: [
    { id: "event_description",          label: "Deviation Event Description",      type: "textarea", placeholder: "What happened, when, where, and how it was discovered…" },
    { id: "impact_assessment",          label: "Impact Assessment",                type: "textarea", placeholder: "Impact on product quality, patient safety, regulatory compliance…" },
    { id: "immediate_actions",          label: "Immediate Actions Taken",          type: "textarea", placeholder: "Steps taken immediately after the deviation was identified…" },
    { id: "root_cause",                 label: "Root Cause (Preliminary)",         type: "textarea", placeholder: "Initial root cause hypothesis or confirmed root cause…" },
    { id: "capa_required",              label: "CAPA Required?",                   type: "text",     placeholder: "Yes / No — and CAPA reference if applicable" },
    { id: "batch_disposition",          label: "Batch Disposition",                type: "text",     placeholder: "e.g. Released, Rejected, Under Review, Quarantine" },
  ],
  "Change Control": [
    { id: "change_type",                label: "Type of Change",                   type: "text",     placeholder: "e.g. Planned / Emergency / Temporary / Permanent" },
    { id: "affected_systems",           label: "Affected Systems / Processes",     type: "textarea", placeholder: "Systems, processes, documents affected by this change…" },
    { id: "impact_assessment",          label: "Impact Assessment",                type: "textarea", placeholder: "GMP impact, product quality impact, regulatory impact…" },
    { id: "validation_impact",          label: "Validation Impact",                type: "text",     placeholder: "e.g. Re-qualification required: OQ, PQ" },
    { id: "approval_levels",            label: "Approval Levels Required",         type: "text",     placeholder: "e.g. QA Head, Regulatory Affairs, Site Director" },
    { id: "implementation_plan",        label: "Implementation Plan",              type: "textarea", placeholder: "Steps and timeline to implement the change…" },
  ],
  "IQ/OQ Combined": [
    { id: "installation_checklist",     label: "Installation Checklist Items",     type: "textarea", placeholder: "Physical installation checks: levelling, anchoring, utility connections…" },
    { id: "calibration_status",         label: "Calibration Status of Instruments",type: "textarea", placeholder: "List instruments and their calibration certificate numbers / due dates…" },
    { id: "operating_parameters",       label: "Operating Parameters to Challenge", type: "textarea", placeholder: "Parameters and their operating ranges (e.g. temperature: 2–8 °C)…" },
    { id: "test_cases",                 label: "Test Cases / Test Scripts",         type: "textarea", placeholder: "List of OQ test cases with test IDs…" },
    { id: "acceptance_criteria",        label: "Acceptance Criteria",               type: "textarea", placeholder: "Pass / fail limits for each test…" },
    { id: "iq_reference",               label: "Related IQ/OQ Reference",           type: "text",     placeholder: "e.g. IQ-OQ-001" },
  ],
  SOP: [
    { id: "procedure_steps",            label: "Key Procedure Steps",              type: "textarea", placeholder: "Outline the main operating steps to be detailed in the SOP…" },
    { id: "safety_precautions",         label: "Safety Precautions",               type: "textarea", placeholder: "PPE requirements, hazards, safety interlocks…" },
    { id: "materials_equipment",        label: "Materials / Equipment Required",   type: "textarea", placeholder: "Consumables, tools, reference standards…" },
    { id: "in_process_controls",        label: "In-Process Controls",              type: "textarea", placeholder: "Parameters monitored during the procedure and their limits…" },
    { id: "training_requirements",      label: "Training Requirements",            type: "textarea", placeholder: "Who must be trained before executing this SOP…" },
    { id: "records_retention",          label: "Records & Retention",              type: "text",     placeholder: "e.g. Logsheets retained for 5 years by QA" },
  ],
  "Validation Plan": [
    { id: "validation_approach",        label: "Validation Approach / Strategy",   type: "textarea", placeholder: "Lifecycle stages to be followed: URS → DQ → IQ → OQ → PQ…" },
    { id: "risk_assessment_summary",    label: "Risk Assessment Summary",          type: "textarea", placeholder: "Methodology and outcome of the risk assessment…" },
    { id: "systems_covered",            label: "Systems / Equipment Covered",      type: "textarea", placeholder: "List all systems, equipment, and utilities in scope…" },
    { id: "deliverables_acceptance",    label: "Deliverables & Acceptance Philosophy", type: "textarea", placeholder: "Documents produced at each stage and how acceptance is determined…" },
    { id: "schedule_timeline",          label: "Schedule / Timeline",              type: "textarea", placeholder: "Target start/completion dates for each validation stage…" },
    { id: "revalidation_criteria",      label: "Revalidation Criteria",            type: "textarea", placeholder: "Triggers for revalidation: relocation, major change, periodic review…" },
  ],
  "Validation Report": [
    { id: "activities_summary",         label: "Summary of Activities Performed",  type: "textarea", placeholder: "URS, DQ, IQ, OQ, PQ activities completed and their outcomes…" },
    { id: "deviations_encountered",     label: "Deviations Encountered",           type: "textarea", placeholder: "Deviations during validation execution and their resolution…" },
    { id: "test_results_summary",       label: "Test Results Summary",             type: "textarea", placeholder: "Overall pass/fail counts across IQ/OQ/PQ…" },
    { id: "traceability_urs",           label: "Traceability to URS",              type: "textarea", placeholder: "Confirmation that all URS requirements were tested and met…" },
    { id: "conclusion_status",          label: "Conclusion / Validation Status",   type: "text",     placeholder: "e.g. Validated, Validated with Restrictions" },
    { id: "periodic_review",            label: "Periodic Review Requirements",     type: "text",     placeholder: "e.g. Annual review, or upon major change" },
  ],
};

function _gdStep4(panel) {
  const questions = GD_QUESTIONS[gdDocType] || [];
  const docs      = window.VALIDATION_DOCS || {};
  const cfg       = docs[gdDocType] || {};

  if (!questions.length) {
    panel.innerHTML = `
      <div class="gd-step-content">
        <h3 class="gd-step-title">Step 4 — Questionnaire</h3>
        <p class="gd-step-sub">No specific questionnaire for ${gdDocType}. Proceed to review.</p>
        <div class="gd-nav-row">
          <button class="gd-btn-secondary" onclick="gdBack()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
          <button class="gd-btn-primary" onclick="gdNext()">Next <span class=\'icon\' data-lucide=\'arrow-right\'></span> Review</button>
        </div>
      </div>`;
    return;
  }

  const saved = gdAnswers;

  panel.innerHTML = `
    <div class="gd-step-content">
      <h3 class="gd-step-title">Step 4 — ${cfg.label || gdDocType} Questionnaire</h3>
      <p class="gd-step-sub">Answer the following questions to provide context for document generation. You may leave optional fields blank.</p>
      <div class="gd-q-list">
        ${questions.map((q, i) => {
          const val = saved[q.id] || "";
          const inp = q.type === "textarea"
            ? `<textarea class="gd-input gd-textarea" id="gq-${q.id}" placeholder="${_gdEscAttr(q.placeholder)}">${_gdEsc(val)}</textarea>`
            : `<input class="gd-input" id="gq-${q.id}" type="text" placeholder="${_gdEscAttr(q.placeholder)}" value="${_gdEscAttr(val)}" />`;
          return `
            <div class="gd-q-item">
              <div class="gd-q-num">Q${i + 1}</div>
              <div class="gd-q-body">
                <label class="gd-q-label">${_gdEsc(q.label)}</label>
                ${inp}
              </div>
            </div>`;
        }).join("")}
      </div>
      <div class="gd-nav-row">
        <button class="gd-btn-secondary" onclick="gdBack()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
        <button class="gd-btn-primary" onclick="gdNext()">Next <span class=\'icon\' data-lucide=\'arrow-right\'></span> Review</button>
      </div>
    </div>`;
}

function _gdCollectAnswers() {
  const questions = GD_QUESTIONS[gdDocType] || [];
  questions.forEach(q => {
    const el = document.getElementById(`gq-${q.id}`);
    if (el) gdAnswers[q.id] = el.value.trim();
  });
}

// ── Step 5: Review Inputs ──────────────────────────────────────────────────────
function _gdStep5(panel) {
  const docs  = window.VALIDATION_DOCS || {};
  const cfg   = docs[gdDocType] || {};
  const qs    = GD_QUESTIONS[gdDocType] || [];

  const eqLabels = {
    equipment_name: "Equipment Name", equipment_id: "Equipment ID",
    manufacturer: "Manufacturer", model: "Model", serial_number: "Serial Number",
    department: "Department", location: "Location", product: "Product",
    software_version: "Software Version", plc_hmi: "PLC / HMI",
    validation_type: "Validation Type",
  };

  const eqRows = Object.entries(eqLabels)
    .filter(([k]) => gdEquipment[k])
    .map(([k, lbl]) => `
      <div class="gd-review-row" data-section="equipment" data-field="${k}">
        <span class="gd-review-key">${lbl}</span>
        <span class="gd-review-val" contenteditable="true" spellcheck="false">${_gdEsc(gdEquipment[k])}</span>
      </div>`).join("");

  const qRows = qs
    .filter(q => gdAnswers[q.id])
    .map(q => `
      <div class="gd-review-row" data-section="answers" data-field="${q.id}">
        <span class="gd-review-key">${_gdEsc(q.label)}</span>
        <span class="gd-review-val" contenteditable="true" spellcheck="false">${_gdEsc(gdAnswers[q.id])}</span>
      </div>`).join("");

  panel.innerHTML = `
    <div class="gd-step-content">
      <h3 class="gd-step-title">Step 5 — Review Inputs</h3>
      <p class="gd-step-sub">Review all collected information. Click any value to edit it inline before generating.</p>

      <div class="gd-review-section">
        <div class="gd-review-section-title">
          <span class="gd-review-badge" style="background:${cfg.color || "#8A6B52"}">${gdDocType}</span>
          <span>${cfg.label || gdDocType}</span>
          <span class="gd-review-project">Project: ${_gdEsc(gdProject?.name || "—")}</span>
        </div>
      </div>

      <div class="gd-review-section">
        <div class="gd-review-header">Equipment Information</div>
        ${eqRows || '<div class="gd-review-empty">No equipment information entered.</div>'}
      </div>

      ${qRows ? `
      <div class="gd-review-section">
        <div class="gd-review-header">${cfg.label || gdDocType} — Questionnaire</div>
        ${qRows}
      </div>` : ""}

      <p class="gd-review-hint"><span class=\'icon\' data-lucide=\'lightbulb\'></span> All fields above are editable. Changes here are saved when you proceed.</p>

      <div class="gd-nav-row">
        <button class="gd-btn-secondary" onclick="gdBack()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
        <button class="gd-btn-primary" onclick="gdNext()">Generate Draft <span class=\'icon\' data-lucide=\'arrow-right\'></span></button>
      </div>
    </div>`;
}

function _gdCollectReview() {
  document.querySelectorAll(".gd-review-row").forEach(row => {
    const section = row.dataset.section;
    const field   = row.dataset.field;
    const el      = row.querySelector(".gd-review-val");
    if (!el) return;
    const val = el.textContent.trim();
    if (section === "equipment") gdEquipment[field] = val;
    if (section === "answers")   gdAnswers[field]   = val;
  });
}

// ── Step 6: Generate Draft ─────────────────────────────────────────────────────
function _gdStep6(panel) {
  panel.innerHTML = `
    <div class="gd-step-content gd-gen-step">
      <h3 class="gd-step-title">Step 6 — Generate Draft</h3>
      <p class="gd-step-sub">All inputs have been compiled. Click <strong>Build Draft</strong> to create the structured document data package.</p>
      <div id="gd-gen-area"></div>
      <div class="gd-nav-row" id="gd-gen-nav">
        <button class="gd-btn-secondary" onclick="gdBack()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
        <button class="gd-btn-generate" id="gd-build-btn" onclick="gdBuildDraft()">
          <span class=\'icon\' data-lucide=\'sparkle\'></span> Build Draft
        </button>
      </div>
    </div>`;
}

async function gdBuildDraft() {
  const btn  = document.getElementById("gd-build-btn");
  const area = document.getElementById("gd-gen-area");
  if (btn) { btn.disabled = true; btn.textContent = "Building…"; }

  // Simulate brief async build
  await new Promise(r => setTimeout(r, 600));

  const docs = window.VALIDATION_DOCS || {};
  const cfg  = docs[gdDocType] || {};
  const qs   = GD_QUESTIONS[gdDocType] || [];
  const now  = new Date().toISOString();

  const questionnaire = {};
  qs.forEach(q => { questionnaire[q.id] = { question: q.label, answer: gdAnswers[q.id] || "" }; });

  gdGeneratedContent = null;
  gdIsGenerating     = false;

  gdDraft = {
    meta: {
      generator:      "PharmaGPT v0.9",
      generated_at:   now,
      status:         "draft",
      doc_number:     _gdGenNumber(gdDocType),
    },
    project: {
      id:   gdProject?.id   || null,
      name: gdProject?.name || null,
    },
    document: {
      type:       gdDocType,
      label:      cfg.label  || gdDocType,
      short:      cfg.short  || gdDocType,
    },
    equipment: { ...gdEquipment },
    questionnaire,
    ai_note: "This JSON package will be submitted to Gemini via Generate Document below to produce the full GMP-compliant document.",
  };

 if (btn) { btn.disabled = false; btn.textContent = "Build Draft"; }

  _gdRenderDraftResult(area);
}

// ── Document number generation ─────────────────────────────────────────────────
function _gdGenNumber(docType) {
  const docs  = window.VALIDATION_DOCS || {};
  const short = (docs[docType]?.short || docType || "DOC").replace(/[^A-Za-z0-9]/g, "");
  const now   = new Date();
  const pad   = n => String(n).padStart(2, "0");
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
  return `${short}-${stamp}`;
}

// Build the form_data payload shared by /validation/generate, /validation/export/docx
// and /validation/save — every doc-number-style key a prompt module might read
// (doc_number / protocol_number / capa_number / …) is set to the same generated
// number so the cover page and body stay consistent regardless of doc type.
function _gdBuildFormData() {
  const docNo   = gdDraft?.meta?.doc_number || _gdGenNumber(gdDocType);
  const details = {
    ...gdAnswers,
    doc_number: docNo, protocol_number: docNo, capa_number: docNo,
    deviation_number: docNo, cc_number: docNo, plan_number: docNo, report_number: docNo,
    version: "1.0",
  };
  return {
    project_name:     gdProject?.name || "",
    project_id:       gdProject?.id   || 0,
    equipment_name:   gdEquipment.equipment_name   || "",
    equipment_id:     gdEquipment.equipment_id     || "",
    manufacturer:     gdEquipment.manufacturer     || "",
    model:            gdEquipment.model            || "",
    serial_number:    gdEquipment.serial_number    || "",
    department:       gdEquipment.department       || "",
    location:         gdEquipment.location         || "",
    product:          gdEquipment.product          || "",
    protocol_number:  docNo,
    revision_number:  "00",
    document_status:  "Draft",
    details,
  };
}

function _gdDocTitle() {
  const docs   = window.VALIDATION_DOCS || {};
  const cfg    = docs[gdDocType] || {};
  const eqName = gdEquipment.equipment_name || "Equipment";
  const docNo  = gdDraft?.meta?.doc_number || _gdGenNumber(gdDocType);
  return `${eqName} — ${cfg.short || gdDocType} ${docNo}`;
}

function _gdRenderDraftResult(area) {
  const docs  = window.VALIDATION_DOCS || {};
  const cfg   = docs[gdDocType] || {};
  const qs    = GD_QUESTIONS[gdDocType] || [];
  const filled = qs.filter(q => gdDraft.questionnaire[q.id]?.answer);

  area.innerHTML = `
    <div class="gd-draft-result">
      <div class="gd-draft-success">
        <span class="gd-draft-check"><span class=\'icon\' data-lucide=\'check\'></span></span>
        <div>
          <strong>Draft package built successfully</strong>
          <div class="gd-draft-sub">Ready for AI generation in v1.0</div>
        </div>
      </div>

      <div class="gd-draft-summary">
        <div class="gd-draft-sum-row">
          <span>Document Type</span>
          <strong style="color:${cfg.color || "#8A6B52"}">${cfg.label || gdDocType}</strong>
        </div>
        <div class="gd-draft-sum-row">
          <span>Project</span>
          <strong>${_gdEsc(gdDraft.project.name || "—")}</strong>
        </div>
        <div class="gd-draft-sum-row">
          <span>Equipment</span>
          <strong>${_gdEsc(gdDraft.equipment.equipment_name || "—")}</strong>
        </div>
        <div class="gd-draft-sum-row">
          <span>Manufacturer</span>
          <strong>${_gdEsc(gdDraft.equipment.manufacturer || "—")}</strong>
        </div>
        <div class="gd-draft-sum-row">
          <span>Department</span>
          <strong>${_gdEsc(gdDraft.equipment.department || "—")}</strong>
        </div>
        <div class="gd-draft-sum-row">
          <span>Questionnaire answers</span>
          <strong>${filled.length} / ${qs.length} filled</strong>
        </div>
        <div class="gd-draft-sum-row">
          <span>Generated at</span>
          <strong>${new Date(gdDraft.meta.generated_at).toLocaleString()}</strong>
        </div>
      </div>

      <div class="gd-draft-json-section">
        <div class="gd-draft-json-header">
          <span>Structured JSON Package</span>
          <button class="gd-chip" onclick="gdCopyJson()"><span class=\'icon\' data-lucide=\'clipboard-list\'></span> Copy JSON</button>
          <button class="gd-chip" onclick="gdDownloadJson()"><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span> Download</button>
        </div>
        <pre class="gd-draft-json" id="gd-draft-json">${_gdEsc(JSON.stringify(gdDraft, null, 2))}</pre>
      </div>

      <div id="gd-ai-section"></div>
    </div>`;

  // Hide Back/Build buttons, show Start Over
  const nav = document.getElementById("gd-gen-nav");
  if (nav) nav.innerHTML = `
    <button class="gd-btn-secondary" onclick="gdBack()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Edit Inputs</button>
    <button class="gd-btn-primary" onclick="openGenDocument()"><span class=\'icon\' data-lucide=\'sparkle\'></span> New Document</button>`;

  _gdRenderAISection();
}

// ══════════════════════════════════════════════════════════════════════════════
// AI DOCUMENT GENERATION (Gemini) — DOCX / PDF / Save to Project Documents
// ══════════════════════════════════════════════════════════════════════════════

function _gdRenderAISection() {
  const section = document.getElementById("gd-ai-section");
  if (!section) return;

  if (!gdGeneratedContent && !gdIsGenerating) {
    section.innerHTML = `
      <div class="gd-ai-teaser">
        <span class="gd-teaser-icon"><span class=\'icon\' data-lucide=\'sparkle\'></span></span>
        <div>
          <strong>Generate the Full GMP Document</strong>
          <p>Submit this draft package to Gemini to generate a full GMP-compliant document with all standard sections, tables, acceptance criteria, and signature blocks.</p>
        </div>
      </div>
      <div class="gd-nav-row" style="justify-content:flex-start">
        <button class="gd-btn-generate" id="gd-generate-btn" onclick="gdGenerateDocument()">
          <span class=\'icon\' data-lucide=\'sparkle\'></span> Generate Document
        </button>
      </div>`;
    return;
  }

  section.innerHTML = `
    <div class="val-viewer-toolbar" style="border-radius:8px;border:1px solid var(--border)">
      <button class="val-tool-btn" onclick="gdGenerateDocument()" title="Regenerate"><span class='icon' data-lucide='refresh-cw'></span> Regenerate</button>
      <div class="val-tool-sep"></div>
      <button class="val-tool-btn val-tool-primary" onclick="gdExportDocx()" id="gd-btn-export-docx" disabled>
        <span class=\'icon\' data-lucide=\'file-text\'></span> Download DOCX
      </button>
      <button class="val-tool-btn val-tool-primary" onclick="gdExportPdf()" id="gd-btn-export-pdf" disabled>
        <span class=\'icon\' data-lucide=\'printer\'></span> Download PDF
      </button>
      <button class="val-tool-btn val-tool-save" onclick="gdSaveToProjectDocuments()" id="gd-btn-save-doc" disabled>
        <span class=\'icon\' data-lucide=\'save\'></span> Save to Project Documents
      </button>
      <div class="val-tool-sep"></div>
      <span class="val-tool-label" id="gd-gen-label"><span class="val-gen-dot"></span> Generating…</span>
    </div>
    <div id="gd-review-banner" style="display:none;margin-top:10px"></div>
    <div class="val-doc-scroll" style="max-height:520px;margin-top:10px;border:1px solid var(--border);border-radius:8px">
      <div class="val-doc-page" style="box-shadow:none">
        <div id="gd-doc-content" class="val-doc-content"><div class="val-streaming-cursor"></div></div>
      </div>
    </div>`;
}

async function gdGenerateDocument() {
  if (gdIsGenerating) return;
  if (!gdProject) { _gdShowError("Please select a project first (Step 1)."); return; }

  gdIsGenerating     = true;
  gdGenAbort         = false;
  gdGeneratedContent = "";
  _gdRenderAISection();

  const label = document.getElementById("gd-gen-label");

  try {
    const res = await fetch("/validation/generate", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        doc_type:   gdDocType,
        project_id: gdProject.id,
        form_data:  _gdBuildFormData(),
        doc_ids:    [],
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer    = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (gdGenAbort) return;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;

        let event;
        try { event = JSON.parse(line.slice(5).trim()); } catch { continue; }

        if (event.error) { _gdShowGenError(event.error); return; }

        if (event.chunk) {
          gdGeneratedContent += event.chunk;

          // Safety net: bail out of a pathological/runaway generation instead
          // of freezing the tab on repeated full-document re-renders.
          if (gdGeneratedContent.length > 400000) {
            _gdShowGenError("The AI response grew unexpectedly large and was stopped. Please try again.");
            try { await reader.cancel(); } catch {}
            return;
          }

          const el = document.getElementById("gd-doc-content");
          if (el) {
            el.innerHTML = marked.parse(gdGeneratedContent) + '<span class="val-cursor-blink">▍</span>';
            const scroll = el.closest(".val-doc-scroll");
            if (scroll) scroll.scrollTop = scroll.scrollHeight;
          }
        }

        if (event.done) _gdFinalizeGeneration();
      }
    }
  } catch (err) {
    _gdShowGenError(err.message || "Generation failed.");
  }
}

function _gdFinalizeGeneration() {
  gdIsGenerating = false;

  const el = document.getElementById("gd-doc-content");
  if (el) el.innerHTML = marked.parse(gdGeneratedContent);

  const label = document.getElementById("gd-gen-label");
  if (label) {
    label.innerHTML = `<span class="val-done-dot"></span> Document ready`;
    label.className = "val-tool-label done";
  }

  ["gd-btn-export-docx", "gd-btn-export-pdf", "gd-btn-save-doc"].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = false;
  });

  _gdRunReviewBadge();
}

function _gdShowGenError(msg) {
  gdIsGenerating = false;
  const el = document.getElementById("gd-doc-content");
  if (el) {
    el.innerHTML = `<div class="val-gen-error">
      <span class='icon' data-lucide='alert-triangle'></span> Generation failed: ${_gdEsc(msg)}
    </div>
    <div class="gd-nav-row" style="justify-content:flex-start;margin-top:10px">
      <button class="gd-btn-primary" onclick="gdGenerateDocument()"><span class='icon' data-lucide='refresh-cw'></span> Retry</button>
    </div>`;
  }
  const label = document.getElementById("gd-gen-label");
  if (label) { label.innerHTML = "Generation failed"; label.className = "val-tool-label"; }
}

async function _gdRunReviewBadge() {
  const banner = document.getElementById("gd-review-banner");
  if (!banner) return;

  banner.style.display = "block";
  banner.innerHTML = `<div class="val-review-loading">Running QA Review…</div>`;

  try {
    const res = await fetch("/validation/review", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content:   gdGeneratedContent,
        doc_type:  gdDocType,
        form_data: _gdBuildFormData(),
      }),
    });
    if (!res.ok) throw new Error("Review request failed");
    const data = await res.json();

    const score     = data.overall_score ?? 0;
    const readiness = data.readiness    ?? "Unknown";
    const summary   = data.issue_summary ?? {};
    const badgeCls  = score >= 85 ? "val-review-badge-green"
                    : score >= 70 ? "val-review-badge-yellow"
                    :               "val-review-badge-red";

    banner.innerHTML = `
      <div class="val-review-banner-inner">
        <div class="val-review-score-wrap ${badgeCls}">
          <span class="val-review-score-num">${score.toFixed(1)}</span>
          <span class="val-review-score-label">/ 100</span>
        </div>
        <div class="val-review-meta">
          <div class="val-review-readiness">${readiness}</div>
          <div class="val-review-counts">
            <span class="vrc-critical">C: ${summary.critical ?? 0}</span>
            <span class="vrc-major">M: ${summary.major ?? 0}</span>
            <span class="vrc-minor">m: ${summary.minor ?? 0}</span>
            <span class="vrc-obs">O: ${summary.observation ?? 0}</span>
          </div>
        </div>
        <div class="val-review-hint">Review Report included in DOCX export</div>
      </div>`;
  } catch {
    banner.innerHTML = `<div class="val-review-loading" style="color:#9A948C">QA review unavailable</div>`;
  }
}

// ── Download DOCX ──────────────────────────────────────────────────────────────
async function gdExportDocx() {
  if (!gdGeneratedContent) return;
  const title = _gdDocTitle();

  try {
    const res = await fetch("/validation/export/docx", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        doc_type:  gdDocType,
        title:     title,
        form_data: _gdBuildFormData(),
        content:   gdGeneratedContent,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `${title}.docx`; a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    _gdShowToast(`DOCX export failed: ${err.message}`, "error");
  }
}

// ── Download PDF (print-to-PDF, same mechanism as the Validation wizard) ──────
function gdExportPdf() {
  if (!gdGeneratedContent) return;
  const content = document.getElementById("gd-doc-content")?.innerHTML || "";
  const win = window.open("", "_blank", "width=900,height=700");
  if (!win) { _gdShowToast("Pop-up blocked — please allow pop-ups to download the PDF.", "error"); return; }

  win.document.write(`<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>${_gdEsc(_gdDocTitle())}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Calibri, 'Segoe UI', sans-serif; font-size: 11pt; color: #5B4C43; background: #FFF; padding: 20mm 25mm; }
  h1 { font-size: 18pt; color: #5B4C43; text-align: center; margin: 0 0 8pt; }
  h2 { font-size: 13pt; color: #5B4C43; border-bottom: 1.5pt solid #8A6B52; padding-bottom: 3pt; margin: 14pt 0 6pt; }
  h3 { font-size: 11.5pt; color: #8A6B52; margin: 10pt 0 4pt; }
  h4 { font-size: 10.5pt; margin: 8pt 0 3pt; }
  p, li { line-height: 1.55; margin: 4pt 0; }
  ul, ol { padding-left: 18pt; }
  table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9.5pt; }
  th { background: #5B4C43; color: #FFF; padding: 6pt 8pt; text-align: left; font-weight: 600; }
  td { padding: 5pt 8pt; border-bottom: 0.5pt solid #EEE7E1; }
  tr:nth-child(even) td { background: #F1ECE6; }
  hr { border: none; border-top: 1pt solid #EEE7E1; margin: 10pt 0; }
  strong { color: #5B4C43; }
  @media print { body { padding: 15mm 20mm; } }
</style>
</head>
<body>${content}</body>
</html>`);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 500);
}

// ── Save to Project Documents ──────────────────────────────────────────────────
async function gdSaveToProjectDocuments() {
  if (!gdGeneratedContent || !gdProject) return;

  const btn = document.getElementById("gd-btn-save-doc");
  if (btn) { btn.disabled = true; btn.innerHTML = "Saving…"; }

  const title    = _gdDocTitle();
  const formData = _gdBuildFormData();

  try {
    // 1. Build the DOCX and upload it into the project's Documents library.
    const docxRes = await fetch("/validation/export/docx", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_type: gdDocType, title, form_data: formData, content: gdGeneratedContent }),
    });
    if (!docxRes.ok) throw new Error(`DOCX build failed (HTTP ${docxRes.status})`);
    const blob = await docxRes.blob();

    const upload = new FormData();
    upload.append("file", blob, `${title}.docx`);
    const uploadRes = await fetch(`/projects/${gdProject.id}/documents`, { method: "POST", body: upload });
    if (!uploadRes.ok) throw new Error(`Upload to Project Documents failed (HTTP ${uploadRes.status})`);

    // 2. Also record it in the project's generated-documents library (powers
    //    the "Protocols Generated" dashboard stat and Recent Activity feed).
    await fetch("/validation/save", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: gdProject.id,
        doc_type:   gdDocType,
        title,
        form_data:  formData,
        content:    gdGeneratedContent,
      }),
    });

    if (btn) { btn.innerHTML = `<span class='icon' data-lucide='check'></span> Saved to Project Documents`; }
    if (window.refreshIcons) window.refreshIcons();
    _gdShowToast("Document saved to Project Documents.", "success");
  } catch (err) {
    if (btn) { btn.disabled = false; btn.innerHTML = `<span class='icon' data-lucide='save'></span> Save to Project Documents`; }
    if (window.refreshIcons) window.refreshIcons();
    _gdShowToast(`Save failed: ${err.message}`, "error");
  }
}

function gdCopyJson() {
  if (!gdDraft) return;
  navigator.clipboard.writeText(JSON.stringify(gdDraft, null, 2))
 .then(() => { const b = event.target; b.textContent = "Copied!"; setTimeout(() => b.textContent = "Copy JSON", 2000); })
    .catch(() => alert("Copy failed — please select and copy manually."));
}

function gdDownloadJson() {
  if (!gdDraft) return;
  const docs   = window.VALIDATION_DOCS || {};
  const cfg    = docs[gdDocType] || {};
  const eqName = gdDraft.equipment.equipment_name || "Equipment";
  const fname  = `${eqName} — ${cfg.short || gdDocType} Draft.json`.replace(/[\\/:*?"<>|]/g, "_");
  const blob   = new Blob([JSON.stringify(gdDraft, null, 2)], { type: "application/json" });
  const url    = URL.createObjectURL(blob);
  const a      = document.createElement("a");
  a.href = url; a.download = fname; a.click();
  URL.revokeObjectURL(url);
}

// ── Navigation ─────────────────────────────────────────────────────────────────
function gdNext() {
  if (gdStep === 1) {
    if (!gdProject) { _gdShowError("Please select a project to continue."); return; }
  }

  if (gdStep === 2) {
    if (!gdDocType) { _gdShowError("Please select a document type to continue."); return; }
  }

  if (gdStep === 3) {
    _gdCollectEquipment();
    if (!gdEquipment.equipment_name) { _gdShowError("Equipment Name is required."); return; }
  }

  if (gdStep === 4) {
    _gdCollectAnswers();
  }

  if (gdStep === 5) {
    _gdCollectReview();
  }

  if (gdStep < 6) _gdRenderStep(gdStep + 1);
}

function gdBack() {
  if (gdStep === 4) _gdCollectAnswers();
  if (gdStep === 5) _gdCollectReview();
  if (gdStep > 1) _gdRenderStep(gdStep - 1);
}

// Capture whatever the current step has typed/selected into gdEquipment /
// gdAnswers before navigating away (Save Draft / Back to Project / Cancel),
// without advancing the wizard step.
function _gdCollectCurrentStep() {
  if (gdStep === 3) _gdCollectEquipment();
  if (gdStep === 4) _gdCollectAnswers();
  if (gdStep === 5) _gdCollectReview();
}

// ── Wizard-level navigation (breadcrumb toolbar) ───────────────────────────────

function _gdHasProgress() {
  return !!(gdDocType || Object.keys(gdEquipment).some(k => gdEquipment[k]) ||
            Object.keys(gdAnswers).some(k => gdAnswers[k]));
}

// Actually leaves the wizard and returns to the project (Chat view) or the
// Dashboard, with no confirmation — callers (gdBackToProject / gdCancel) are
// responsible for confirming first.
function _gdLeaveToProject() {
  if (window.Workspace) window.Workspace.exit();
  if (gdProject && window.selectProject) {
    window.selectProject(gdProject);
  }
  if (window.showView) {
    window.showView(gdProject ? "view-chat" : "view-dashboard");
  }
  // Keep the sidebar highlight in sync with whichever view we just switched to.
  document.querySelectorAll(".sidebar-item[data-view]").forEach(n => n.classList.remove("active"));
  const nav = document.getElementById(gdProject ? "nav-chat" : "nav-dashboard");
  if (nav) nav.classList.add("active");
  if (!gdProject && window.loadDashboard) window.loadDashboard();
}

async function gdBackToProject() {
  _gdCollectCurrentStep();
  if (_gdHasProgress()) {
    const ok = window.Workspace
      ? await window.Workspace.confirmDialog({
          title: "Leave Generate Document?",
          message: "Unsaved progress will be lost unless you Save Draft first.",
          confirmLabel: "Leave", cancelLabel: "Stay", danger: true,
        })
      : confirm("Leave Generate Document? Unsaved progress will be lost unless you Save Draft first.");
    if (!ok) return;
  }
  _gdLeaveToProject();
}

async function gdCancel() {
  _gdCollectCurrentStep();
  if (_gdHasProgress()) {
    const ok = window.Workspace
      ? await window.Workspace.confirmDialog({
          title: "Discard changes?",
          message: "All progress on this document will be discarded.",
          confirmLabel: "Yes", cancelLabel: "No", danger: true,
        })
      : confirm("Cancel document generation? All progress on this document will be discarded.");
    if (!ok) return;
  }
  _gdLeaveToProject();
}

async function gdSaveDraft() {
  _gdCollectCurrentStep();

  if (!gdProject) {
    _gdShowToast("Select a project first (Step 1) before saving a draft.", "error");
    return;
  }

  const docType = gdDocType || "DRAFT";
  const payload = {
    project_id: gdProject.id,
    doc_type:   docType,
    title:      `${docType} — Draft (${new Date().toLocaleString()})`,
    form_data:  { equipment: gdEquipment, answers: gdAnswers, step: gdStep },
    // `content` is required by the save endpoint; a real markdown draft isn't
    // generated until Step 6 (AI generation is deferred to v1.0), so persist
    // the structured inputs collected so far as the placeholder content.
    content:    JSON.stringify({ equipment: gdEquipment, answers: gdAnswers }, null, 2),
  };

  try {
    const res = await fetch("/validation/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("Save failed");
    _gdShowToast("Draft saved to project.", "success");
  } catch {
    _gdShowToast("Could not save draft. Please try again.", "error");
  }
}

function _gdShowError(msg) {
  _gdShowToast(msg, "error");
}

function _gdShowToast(msg, kind) {
  let el = document.getElementById("gd-error-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "gd-error-toast";
    el.className = "gd-error-toast";
    document.body.appendChild(el);
  }
  el.classList.toggle("success", kind === "success");
  el.textContent = msg;
  el.classList.add("visible");
  setTimeout(() => el.classList.remove("visible"), 3000);
}

// ── Utility ────────────────────────────────────────────────────────────────────
function _gdEsc(str) {
  return String(str || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function _gdEscAttr(str) {
  return String(str || "").replace(/"/g, "&quot;");
}

// ── Global exports ─────────────────────────────────────────────────────────────
window.openGenDocument  = openGenDocument;
window.gdNext           = gdNext;
window.gdBack           = gdBack;
window.gdBackToProject  = gdBackToProject;
window.gdSaveDraft      = gdSaveDraft;
window.gdCancel         = gdCancel;
window.gdSelectProject  = gdSelectProject;
window.gdSelectDocType  = gdSelectDocType;
window.gdBuildDraft     = gdBuildDraft;
window.gdCopyJson       = gdCopyJson;
window.gdDownloadJson   = gdDownloadJson;
window.gdHasUnsavedChanges = _gdHasProgress;
window.gdGenerateDocument      = gdGenerateDocument;
window.gdExportDocx            = gdExportDocx;
window.gdExportPdf              = gdExportPdf;
window.gdSaveToProjectDocuments = gdSaveToProjectDocuments;
