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
 */

const VALIDATION_DOCS = {

  URS: {
    label: "User Requirement Specification",
    short: "URS",
    icon: "📋",
    color: "#7B1FA2",
    step2: [
      { id: "doc_number",    label: "Document Number",   placeholder: "URS-001",         required: true  },
      { id: "version",       label: "Version",           placeholder: "1.0",             required: true  },
      { id: "system_name",   label: "System / Equipment Name", placeholder: "e.g. HPLC System" },
      { id: "intended_use",  label: "Intended Use",      placeholder: "Describe the intended use of the system...", type: "textarea" },
    ],
  },

  DQ: {
    label: "Design Qualification",
    short: "DQ",
    icon: "📐",
    color: "#E65100",
    step2: [
      { id: "doc_number",  label: "Document Number", placeholder: "DQ-001", required: true },
      { id: "version",     label: "Version",         placeholder: "1.0",    required: true },
      { id: "vendor_name", label: "Vendor / Supplier Name", placeholder: "e.g. Agilent Technologies" },
    ],
  },

  FAT: {
    label: "Factory Acceptance Testing",
    short: "FAT",
    icon: "🏭",
    color: "#827717",
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
    icon: "🔩",
    color: "#4E342E",
    step2: [
      { id: "doc_number",  label: "Document Number",  placeholder: "SAT-001", required: true },
      { id: "version",     label: "Version",          placeholder: "1.0",     required: true },
      { id: "sat_date",    label: "Planned SAT Date", placeholder: "DD-Mon-YYYY", type: "date" },
      { id: "fat_ref",     label: "FAT Reference No", placeholder: "FAT-001" },
    ],
  },

  IQ: {
    label: "Installation Qualification",
    short: "IQ",
    icon: "🔧",
    color: "#1B5E20",
    step2: [
      { id: "protocol_number", label: "Protocol Number",        placeholder: "IQ-001",  required: true },
      { id: "version",         label: "Version",                placeholder: "1.0",     required: true },
      { id: "po_number",       label: "Purchase Order Number",  placeholder: "PO-2026-001" },
      { id: "urs_reference",   label: "URS Reference",          placeholder: "URS-001" },
    ],
  },

  OQ: {
    label: "Operational Qualification",
    short: "OQ",
    icon: "🔬",
    color: "#0D47A1",
    step2: [
      { id: "protocol_number", label: "Protocol Number",         placeholder: "OQ-001",  required: true },
      { id: "version",         label: "Version",                 placeholder: "1.0",     required: true },
      { id: "product",         label: "Product",                 placeholder: "e.g. Paracetamol 500 mg" },
      { id: "batch_size",      label: "Batch Size",              placeholder: "e.g. 100,000 tablets" },
      { id: "urs_reference",   label: "User Requirement Reference", placeholder: "URS-001" },
    ],
  },

  PQ: {
    label: "Performance Qualification",
    short: "PQ",
    icon: "📊",
    color: "#006064",
    step2: [
      { id: "protocol_number", label: "Protocol Number",    placeholder: "PQ-001",  required: true },
      { id: "version",         label: "Version",            placeholder: "1.0",     required: true },
      { id: "product",         label: "Product",            placeholder: "e.g. Amoxicillin 250 mg" },
      { id: "batch_size",      label: "Batch Size",         placeholder: "e.g. 50,000 capsules" },
      { id: "number_of_runs",  label: "Number of PQ Runs",  placeholder: "3" },
      { id: "urs_reference",   label: "OQ Reference",       placeholder: "OQ-001" },
    ],
  },

  FMEA: {
    label: "Failure Mode and Effects Analysis",
    short: "FMEA",
    icon: "⚠️",
    color: "#B71C1C",
    step2: [
      { id: "doc_number",   label: "FMEA Document Number", placeholder: "FMEA-001", required: true },
      { id: "version",      label: "Version",              placeholder: "1.0",      required: true },
      { id: "fmea_scope",   label: "FMEA Scope",           placeholder: "e.g. Full HPLC system — all critical components", type: "textarea" },
    ],
  },

  CAPA: {
    label: "Corrective and Preventive Action",
    short: "CAPA",
    icon: "🔄",
    color: "#1A237E",
    step2: [
      { id: "capa_number",  label: "CAPA Number",   placeholder: "CAPA-001",              required: true },
      { id: "version",      label: "Version",        placeholder: "1.0",                   required: true },
      { id: "capa_source",  label: "CAPA Source",    placeholder: "e.g. Internal Audit, Deviation, Customer Complaint" },
      { id: "description",  label: "Issue Description", placeholder: "Describe the problem / non-conformance...", type: "textarea" },
    ],
  },

  Deviation: {
    label: "Deviation Report",
    short: "DEV",
    icon: "⚡",
    color: "#E65100",
    step2: [
      { id: "deviation_number", label: "Deviation Number", placeholder: "DEV-001",                      required: true },
      { id: "version",          label: "Version",          placeholder: "1.0",                          required: true },
      { id: "category",         label: "Deviation Category", placeholder: "e.g. Planned / Unplanned / Critical" },
      { id: "description",      label: "Deviation Description", placeholder: "What happened, when, where, how discovered...", type: "textarea" },
    ],
  },

  "Change Control": {
    label: "Change Control",
    short: "CC",
    icon: "🔀",
    color: "#37474F",
    step2: [
      { id: "cc_number",           label: "Change Control Number", placeholder: "CC-001",            required: true },
      { id: "version",             label: "Version",               placeholder: "1.0",               required: true },
      { id: "change_description",  label: "Description of Change", placeholder: "What is changing...", type: "textarea" },
      { id: "reason_for_change",   label: "Reason / Justification", placeholder: "Why is this change needed...", type: "textarea" },
    ],
  },

};

// Ordered list for the sidebar (controls display order)
const VALIDATION_DOC_ORDER = [
  "URS", "DQ", "FAT", "SAT", "IQ", "OQ", "PQ",
  "FMEA", "CAPA", "Deviation", "Change Control",
];

// Expose globally for validation.js and index.html
window.VALIDATION_DOCS      = VALIDATION_DOCS;
window.VALIDATION_DOC_ORDER = VALIDATION_DOC_ORDER;
