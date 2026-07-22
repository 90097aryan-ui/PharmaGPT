/**
 * validation_config.js — Document type definitions for the Validation Wizard.
 *
 * Each entry defines:
 *   label    : human-readable document name
 *   short    : abbreviation shown in the document viewer
 *   icon     : emoji icon for sidebar and viewer
 *   color    : hex accent colour for the document type badge
 *   step2    : array of field definitions for Step 2 of the wizard
 *
 * To add a new document type: add an entry to VALIDATION_DOCS and add
 * the corresponding prompt builder in services/doc_generator.py.
 *
 * URS, IQ, OQ, PQ, CAPA, Deviation, and Change Control are deliberately NOT
 * listed here: each now has its own dedicated, more capable suite (URS
 * Management, Qualification, QMS CAPA/Deviation/Change Control) with its own
 * "Generate with AI" entry point, lifecycle, and approval trail. Offering a
 * second, thinner generation path for the same document type here was a
 * Critical finding (REPOSITORY_AUDIT.md, DUPLICATE_FUNCTION_ANALYSIS.md §1) —
 * retired per Blueprint ADR-P02, enforced server-side too (see
 * routes/validation.py::_RETIRED_DOC_TYPES). Do not re-add them here.
 */

const VALIDATION_DOCS = {

  DQ: {
    label: "Design Qualification",
    short: "DQ",
    icon: "<span class=\'icon\' data-lucide=\'ruler\'></span>",
    color: "#A97D2E",
    step2: [
      { id: "doc_number",  label: "Document Number", placeholder: "DQ-001", required: true },
      { id: "version",     label: "Version",         placeholder: "1.0",    required: true },
      { id: "vendor_name", label: "Vendor / Supplier Name", placeholder: "e.g. Agilent Technologies" },
    ],
  },

  FAT: {
    label: "Factory Acceptance Testing",
    short: "FAT",
    icon: "<span class=\'icon\' data-lucide=\'factory\'></span>",
    color: "#C59A41",
    step2: [
      { id: "doc_number",    label: "Document Number",     placeholder: "FAT-001", required: true },
      { id: "version",       label: "Version",             placeholder: "1.0",     required: true },
      { id: "fat_date",      label: "Planned FAT Date",    placeholder: "DD-Mon-YYYY", type: "date" },
      { id: "fat_location",  label: "FAT Location",        placeholder: "Manufacturer's facility address" },
    ],
  },

  SAT: {
    label: "Site Acceptance Testing",
    short: "SAT",
    icon: "<span class=\'icon\' data-lucide=\'wrench\'></span>",
    color: "#2D2A28",
    step2: [
      { id: "doc_number",  label: "Document Number",  placeholder: "SAT-001", required: true },
      { id: "version",     label: "Version",          placeholder: "1.0",     required: true },
      { id: "sat_date",    label: "Planned SAT Date", placeholder: "DD-Mon-YYYY", type: "date" },
      { id: "fat_ref",     label: "FAT Reference No", placeholder: "FAT-001" },
    ],
  },

  FMEA: {
    label: "Failure Mode and Effects Analysis",
    short: "FMEA",
    icon: "<span class=\'icon\' data-lucide=\'alert-triangle\'></span>",
    color: "#A8544F",
    step2: [
      { id: "doc_number",   label: "FMEA Document Number", placeholder: "FMEA-001", required: true },
      { id: "version",      label: "Version",              placeholder: "1.0",      required: true },
      { id: "fmea_scope",   label: "FMEA Scope",           placeholder: "e.g. Full HPLC system — all critical components", type: "textarea" },
    ],
  },

  "IQ/OQ Combined": {
    label: "Combined Installation & Operational Qualification",
    short: "IQ/OQ",
    icon: "<span class=\'icon\' data-lucide=\'wrench\'></span>",
    color: "#4C7A4E",
    step2: [
      { id: "protocol_number", label: "Protocol Number",        placeholder: "IQ-OQ-001", required: true },
      { id: "version",         label: "Version",                placeholder: "1.0",       required: true },
      { id: "po_number",       label: "Purchase Order Number",  placeholder: "PO-2026-001" },
      { id: "urs_reference",   label: "URS Reference",          placeholder: "URS-001" },
    ],
  },

  SOP: {
    label: "Standard Operating Procedure",
    short: "SOP",
    icon: "<span class=\'icon\' data-lucide=\'file-text\'></span>",
    color: "#3D6140",
    step2: [
      { id: "doc_number",        label: "Document Number",     placeholder: "SOP-001", required: true },
      { id: "version",           label: "Version",             placeholder: "1.0",     required: true },
      { id: "sop_title",         label: "SOP Title",           placeholder: "e.g. Operation and Use of HPLC System" },
      { id: "department_owner",  label: "Owning Department",   placeholder: "e.g. Quality Control" },
    ],
  },

  "Validation Plan": {
    label: "Validation Plan",
    short: "VMP",
    icon: "<span class=\'icon\' data-lucide=\'list-checks\'></span>",
    color: "#8A6B52",
    step2: [
      { id: "plan_number",       label: "Plan Number",          placeholder: "VMP-001", required: true },
      { id: "version",           label: "Version",              placeholder: "1.0",     required: true },
      { id: "validation_scope",  label: "Validation Scope",     placeholder: "e.g. HPLC System and associated systems", type: "textarea" },
      { id: "risk_category",     label: "Risk Category",        placeholder: "e.g. High / Medium / Low" },
    ],
  },

  "Validation Report": {
    label: "Validation Summary Report",
    short: "VSR",
    icon: "<span class=\'icon\' data-lucide=\'bar-chart-3\'></span>",
    color: "#5B4C43",
    step2: [
      { id: "report_number",       label: "Report Number",        placeholder: "VSR-001", required: true },
      { id: "version",             label: "Version",              placeholder: "1.0",     required: true },
      { id: "plan_reference",      label: "Validation Plan Reference", placeholder: "VMP-001" },
      { id: "activities_covered",  label: "Activities Covered",   placeholder: "e.g. URS, DQ, IQ, OQ, PQ" },
    ],
  },

};

// Ordered list for the sidebar (controls display order)
const VALIDATION_DOC_ORDER = [
  "DQ", "FAT", "SAT", "IQ/OQ Combined",
  "SOP", "Validation Plan", "Validation Report",
  "FMEA",
];

// Expose globally for validation.js and index.html
window.VALIDATION_DOCS      = VALIDATION_DOCS;
window.VALIDATION_DOC_ORDER = VALIDATION_DOC_ORDER;
