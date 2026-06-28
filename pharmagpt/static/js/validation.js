/**
 * validation.js — Validation Document Generator wizard.
 *
 * Phases:
 *   1. WIZARD  — 4-step form (Equipment → Details → Documents → Generate)
 *   2. VIEWER  — Word-like document viewer with export buttons
 *
 * The wizard is document-type–agnostic: step 2 fields are rendered
 * dynamically from validation_config.js (VALIDATION_DOCS[docType].step2).
 *
 * Dependencies (load order in index.html):
 *   validation_config.js → validation.js
 */

// ── State ─────────────────────────────────────────────────────────────────────
let valDocType       = "OQ";      // active document type
let valStep          = 1;         // current wizard step (1–4)
let valFormData      = {};        // accumulated Step-1 and Step-2 fields
let valSelectedDocs  = [];        // doc IDs selected in Step 3
let valDocList       = [];        // project documents loaded in Step 3
let valGeneratedText = "";        // full markdown returned by Gemini
let valIsGenerating  = false;

// ── Entry point: called when a doc-type sidebar item is clicked ───────────────

function openValidationWizard(docType) {
  valDocType = docType;
  valStep    = 1;
  valFormData = {};
  valSelectedDocs  = [];
  valGeneratedText = "";
  valIsGenerating  = false;

  const cfg = window.VALIDATION_DOCS[docType] || {};
  document.getElementById("val-doc-type-title").textContent = cfg.label || docType;
  document.getElementById("val-doc-type-sub").textContent   = cfg.short ? `${cfg.short} — Protocol Generator` : "Protocol Generator";
  document.getElementById("val-doc-type-badge").textContent = cfg.short || docType;
  document.getElementById("val-doc-type-badge").style.background = cfg.color || "#1565C0";

  // Hide viewer, show wizard
  document.getElementById("val-wizard").style.display    = "flex";
  document.getElementById("val-viewer").style.display    = "none";

  _renderStep(1);
}

// ── Step rendering ────────────────────────────────────────────────────────────

function _renderStep(n) {
  valStep = n;
  _updateProgress(n);

  // Hide all step panels
  [1, 2, 3, 4].forEach(i => {
    const el = document.getElementById(`val-panel-${i}`);
    if (el) el.style.display = "none";
  });

  const panel = document.getElementById(`val-panel-${n}`);
  if (!panel) return;
  panel.style.display = "flex";

  // Step-specific setup
  if (n === 1) _setupStep1(panel);
  if (n === 2) _setupStep2(panel);
  if (n === 3) _setupStep3(panel);
  if (n === 4) _setupStep4(panel);
}

function _updateProgress(activeStep) {
  [1, 2, 3, 4].forEach(i => {
    const dot  = document.getElementById(`vstep-dot-${i}`);
    const lbl  = document.getElementById(`vstep-lbl-${i}`);
    const line = document.getElementById(`vstep-line-${i}`);
    if (!dot) return;
    if (i < activeStep) {
      dot.className = "val-step-dot done";
      lbl.className = "val-step-label done";
    } else if (i === activeStep) {
      dot.className = "val-step-dot active";
      lbl.className = "val-step-label active";
    } else {
      dot.className = "val-step-dot";
      lbl.className = "val-step-label";
    }
    if (line) line.className = i < activeStep ? "val-step-line done" : "val-step-line";
  });
}

// ── Step 1: Equipment Details ─────────────────────────────────────────────────

function _setupStep1(panel) {
  // Pre-fill from active project if available
  const proj = window.activeProject;

  const fields = [
    { id: "equipment_name", label: "Equipment Name *", placeholder: "e.g. HPLC System", value: proj?.equipment_name || "" },
    { id: "model",          label: "Model / Type",     placeholder: "e.g. Agilent 1260 Infinity II",  value: "" },
    { id: "manufacturer",   label: "Manufacturer",     placeholder: "e.g. Agilent Technologies",      value: proj?.manufacturer || "" },
    { id: "serial_number",  label: "Serial Number",    placeholder: "e.g. DE12345678",                value: "" },
    { id: "location",       label: "Installation Location", placeholder: "e.g. Lab 3, Building B",   value: "" },
    { id: "department",     label: "Department",        placeholder: "e.g. Quality Control",          value: proj?.department || "" },
  ];

  panel.innerHTML = `
    <div class="val-step-content">
      <h3 class="val-step-title">Step 1 — Equipment Details</h3>
      <p class="val-step-sub">Enter the equipment information that will appear on the document header.</p>
      <div class="val-form-grid">
        ${fields.map(f => `
          <div class="val-form-group">
            <label class="val-label">${f.label}</label>
            <input class="val-input" id="vf-${f.id}" placeholder="${f.placeholder}" value="${escapeAttr(f.value)}" />
          </div>`).join("")}
      </div>
      <div class="val-nav-row">
        <span></span>
        <button class="val-btn-primary" onclick="valNext()">Next → Step 2</button>
      </div>
    </div>
  `;
}

// ── Step 2: Document-specific fields ─────────────────────────────────────────

function _setupStep2(panel) {
  const cfg    = window.VALIDATION_DOCS[valDocType] || {};
  const fields = cfg.step2 || [];

  const fieldsHtml = fields.map(f => {
    if (f.type === "textarea") {
      return `
        <div class="val-form-group val-full-width">
          <label class="val-label">${f.label}${f.required ? " *" : ""}</label>
          <textarea class="val-input val-textarea" id="vf2-${f.id}" placeholder="${f.placeholder || ""}"></textarea>
        </div>`;
    }
    return `
      <div class="val-form-group">
        <label class="val-label">${f.label}${f.required ? " *" : ""}</label>
        <input class="val-input" type="${f.type || "text"}" id="vf2-${f.id}" placeholder="${f.placeholder || ""}" />
      </div>`;
  }).join("");

  panel.innerHTML = `
    <div class="val-step-content">
      <h3 class="val-step-title">Step 2 — ${cfg.label || valDocType} Details</h3>
      <p class="val-step-sub">Provide the document-specific information for this ${cfg.short || valDocType}.</p>
      <div class="val-form-grid">
        ${fieldsHtml || "<p class='val-note'>No additional fields required for this document type.</p>"}
      </div>
      <div class="val-nav-row">
        <button class="val-btn-secondary" onclick="valBack()">← Back</button>
        <button class="val-btn-primary" onclick="valNext()">Next → Step 3</button>
      </div>
    </div>
  `;
}

// ── Step 3: Document selection ────────────────────────────────────────────────

async function _setupStep3(panel) {
  panel.innerHTML = `
    <div class="val-step-content">
      <h3 class="val-step-title">Step 3 — Reference Documents</h3>
      <p class="val-step-sub">Select uploaded project documents to include as context for the AI generator.</p>
      <div id="val-doc-select-list"><div class="val-loading">Loading documents…</div></div>
      <div class="val-nav-row">
        <button class="val-btn-secondary" onclick="valBack()">← Back</button>
        <button class="val-btn-primary" onclick="valNext()">Next → Generate</button>
      </div>
    </div>
  `;

  const list = document.getElementById("val-doc-select-list");

  if (!window.activeProject) {
    list.innerHTML = "<p class='val-note'>No project selected. Documents cannot be loaded.</p>";
    return;
  }

  try {
    const res  = await fetch(`/projects/${window.activeProject.id}/documents`);
    valDocList = await res.json();

    if (valDocList.length === 0) {
      list.innerHTML = `<p class="val-note">No documents uploaded to this project yet.<br>
        You can still generate the document without document context.</p>`;
      return;
    }

    const icons = { pdf: "📄", docx: "📝", xlsx: "📊", txt: "📃" };

    list.innerHTML = `
      <div class="val-doc-select-controls">
        <button class="val-chip" onclick="_valSelectAll(true)">Select All</button>
        <button class="val-chip" onclick="_valSelectAll(false)">Deselect All</button>
        <span class="val-note" id="val-selected-count">${valSelectedDocs.length} selected</span>
      </div>
      ${valDocList.map(d => `
        <label class="val-doc-row" id="val-docrow-${d.id}">
          <input type="checkbox" class="val-doc-chk" data-id="${d.id}"
            onchange="_valToggleDoc(${d.id}, this.checked)"
            ${valSelectedDocs.includes(d.id) ? "checked" : ""} />
          <span class="val-doc-icon">${icons[d.file_type] || "📄"}</span>
          <span class="val-doc-name">${escapeHtmlVal(d.original_name)}</span>
          <span class="val-doc-type-badge">${d.file_type.toUpperCase()}</span>
        </label>`).join("")}
    `;
  } catch {
    list.innerHTML = "<p class='val-note'>Could not load documents.</p>";
  }
}

function _valToggleDoc(docId, checked) {
  if (checked) {
    if (!valSelectedDocs.includes(docId)) valSelectedDocs.push(docId);
  } else {
    valSelectedDocs = valSelectedDocs.filter(id => id !== docId);
  }
  const cnt = document.getElementById("val-selected-count");
  if (cnt) cnt.textContent = `${valSelectedDocs.length} selected`;
}

function _valSelectAll(checked) {
  valSelectedDocs = checked ? valDocList.map(d => d.id) : [];
  document.querySelectorAll(".val-doc-chk").forEach(chk => {
    chk.checked = checked;
  });
  const cnt = document.getElementById("val-selected-count");
  if (cnt) cnt.textContent = `${valSelectedDocs.length} selected`;
}

// ── Step 4: Generate ──────────────────────────────────────────────────────────

function _setupStep4(panel) {
  const cfg = window.VALIDATION_DOCS[valDocType] || {};

  panel.innerHTML = `
    <div class="val-step-content">
      <h3 class="val-step-title">Step 4 — Generate Document</h3>
      <p class="val-step-sub">Review your inputs and click Generate to create the ${cfg.label || valDocType}.</p>

      <div class="val-summary-card">
        <div class="val-summary-row"><span>Document Type</span><strong>${cfg.label || valDocType}</strong></div>
        <div class="val-summary-row"><span>Equipment</span><strong>${escapeHtmlVal(valFormData.equipment_name || "—")}</strong></div>
        <div class="val-summary-row"><span>Manufacturer</span><strong>${escapeHtmlVal(valFormData.manufacturer || "—")}</strong></div>
        <div class="val-summary-row"><span>Department</span><strong>${escapeHtmlVal(valFormData.department || "—")}</strong></div>
        <div class="val-summary-row"><span>Reference Docs</span><strong>${valSelectedDocs.length} document(s) selected</strong></div>
      </div>

      <div id="val-gen-status"></div>

      <div class="val-nav-row">
        <button class="val-btn-secondary" onclick="valBack()">← Back</button>
        <button class="val-btn-generate" id="val-gen-btn" onclick="startGeneration()">
          ✦ Generate ${cfg.short || valDocType}
        </button>
      </div>
    </div>
  `;
}

// ── Navigation ────────────────────────────────────────────────────────────────

function valNext() {
  if (valStep === 1) {
    // Collect Step 1
    const fields = ["equipment_name", "model", "manufacturer", "serial_number", "location", "department"];
    fields.forEach(id => {
      const el = document.getElementById(`vf-${id}`);
      if (el) valFormData[id] = el.value.trim();
    });
    if (!valFormData.equipment_name) {
      alert("Equipment Name is required.");
      return;
    }
  }

  if (valStep === 2) {
    // Collect Step 2 into formData.details
    const cfg    = window.VALIDATION_DOCS[valDocType] || {};
    const fields = cfg.step2 || [];
    const details = {};
    let missingRequired = "";
    fields.forEach(f => {
      const el = document.getElementById(`vf2-${f.id}`);
      if (el) {
        details[f.id] = el.value.trim();
        if (f.required && !details[f.id]) missingRequired = f.label;
      }
    });
    if (missingRequired) {
      alert(`"${missingRequired}" is required.`);
      return;
    }
    valFormData.details = details;
  }

  if (valStep < 4) _renderStep(valStep + 1);
}

function valBack() {
  if (valStep > 1) _renderStep(valStep - 1);
}

// ── Generation ────────────────────────────────────────────────────────────────

async function startGeneration() {
  if (valIsGenerating) return;
  if (!window.activeProject) {
    alert("Please select a project first.");
    return;
  }

  valIsGenerating  = true;
  valGeneratedText = "";

  const btn    = document.getElementById("val-gen-btn");
  const status = document.getElementById("val-gen-status");
  if (btn)    btn.disabled = true;
  if (status) status.innerHTML = `<div class="val-gen-progress"><div class="val-gen-dots"><span></span><span></span><span></span></div> Generating ${valDocType} document…</div>`;

  try {
    const res = await fetch("/validation/generate", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        doc_type:   valDocType,
        project_id: window.activeProject.id,
        form_data:  valFormData,
        doc_ids:    valSelectedDocs,
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer    = "";

    // Switch to viewer immediately so user sees content stream in
    document.getElementById("val-wizard").style.display = "none";
    document.getElementById("val-viewer").style.display = "flex";
    _initViewer();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;

        let event;
        try { event = JSON.parse(line.slice(5).trim()); } catch { continue; }

        if (event.error) {
          _showViewerError(event.error);
          return;
        }
        if (event.chunk) {
          valGeneratedText += event.chunk;
          _updateViewerContent(valGeneratedText);
        }
        if (event.done) {
          _finaliseViewer();
        }
      }
    }

  } catch (err) {
    valIsGenerating = false;
    const status2 = document.getElementById("val-gen-status");
    if (status2) status2.innerHTML = `<div class="val-gen-error">Error: ${err.message}</div>`;
    if (btn) btn.disabled = false;
  }
}

// ── Document Viewer ───────────────────────────────────────────────────────────

function _initViewer() {
  const viewer = document.getElementById("val-viewer");
  viewer.innerHTML = `
    <!-- Toolbar -->
    <div class="val-viewer-toolbar">
      <button class="val-tool-btn" onclick="backToWizard()" title="Back to wizard">← Regenerate</button>
      <div class="val-tool-sep"></div>
      <button class="val-tool-btn val-tool-primary" onclick="exportDocx()" id="btn-export-docx" disabled>
        📄 Export DOCX
      </button>
      <button class="val-tool-btn val-tool-primary" onclick="printDocument()" id="btn-export-pdf" disabled>
        🖨 Print / PDF
      </button>
      <button class="val-tool-btn val-tool-save" onclick="saveToProject()" id="btn-save-doc" disabled>
        💾 Save to Project
      </button>
      <div class="val-tool-sep"></div>
      <span class="val-tool-label" id="val-gen-label">
        <span class="val-gen-dot"></span> Generating…
      </span>
    </div>

    <!-- Word-like document page -->
    <div class="val-doc-scroll">
      <div class="val-doc-page" id="val-doc-page">
        <div id="val-doc-content" class="val-doc-content">
          <div class="val-streaming-cursor"></div>
        </div>
      </div>
    </div>
  `;
}

function _updateViewerContent(markdown) {
  const el = document.getElementById("val-doc-content");
  if (!el) return;
  el.innerHTML = marked.parse(markdown) + '<span class="val-cursor-blink">▍</span>';
  // Auto-scroll to bottom
  const scroll = document.querySelector(".val-doc-scroll");
  if (scroll) scroll.scrollTop = scroll.scrollHeight;
}

function _finaliseViewer() {
  valIsGenerating = false;

  const el = document.getElementById("val-doc-content");
  if (el) el.innerHTML = marked.parse(valGeneratedText);

  const label = document.getElementById("val-gen-label");
  if (label) {
    label.innerHTML = `<span class="val-done-dot"></span> Document ready`;
    label.className = "val-tool-label done";
  }

  // Enable export buttons
  ["btn-export-docx", "btn-export-pdf", "btn-save-doc"].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = false;
  });

  // Run review and show score badge
  _runReviewAndShowBadge();
}

async function _runReviewAndShowBadge() {
  const banner = document.getElementById("val-review-banner");
  if (!banner) return;

  banner.style.display = "block";
  banner.innerHTML = `<div class="val-review-loading">Running QA Review…</div>`;

  try {
    const res = await fetch("/validation/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content:   valGeneratedText,
        doc_type:  valDocType,
        form_data: valFormData || {},
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

    // Refresh dashboard score card if visible
    if (window.loadDashboard && document.getElementById("view-dashboard") &&
        document.getElementById("view-dashboard").style.display !== "none") {
      fetch("/dashboard/validation-score")
        .then(r => r.json())
        .then(d => {
          if (typeof renderAvgScore === "function")
            renderAvgScore(d.avg_score || 0, d.doc_count || 0);
        })
        .catch(() => {});
    }
  } catch (err) {
    banner.innerHTML = `<div class="val-review-loading" style="color:#999">QA review unavailable</div>`;
  }
}

function _showViewerError(msg) {
  valIsGenerating = false;
  const el = document.getElementById("val-doc-content");
  if (el) el.innerHTML = `<div class="val-gen-error">⚠ Generation failed: ${escapeHtmlVal(msg)}</div>`;
}

// ── Export / Save ─────────────────────────────────────────────────────────────

async function exportDocx() {
  if (!valGeneratedText) return;

  const cfg     = window.VALIDATION_DOCS[valDocType] || {};
  const details = valFormData.details || {};
  const eqName  = valFormData.equipment_name || "Equipment";
  const proto   = details.protocol_number || details.doc_number || details.capa_number || details.deviation_number || valDocType;
  const title   = `${eqName} — ${cfg.short || valDocType} ${proto}`;

  try {
    const res = await fetch("/validation/export/docx", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        doc_type:  valDocType,
        title:     title,
        form_data: { ...valFormData, project_name: window.activeProject?.name || "" },
        content:   valGeneratedText,
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `${title}.docx`;
    a.click();
    URL.revokeObjectURL(url);

  } catch (err) {
    alert(`DOCX export failed: ${err.message}`);
  }
}

function printDocument() {
  // Open the document page in a print-friendly window
  const content = document.getElementById("val-doc-page")?.innerHTML || "";
  const win = window.open("", "_blank", "width=900,height=700");
  win.document.write(`<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Print Document</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Calibri, 'Segoe UI', sans-serif; font-size: 11pt; color: #1A2B3C; background: #fff; padding: 20mm 25mm; }
  h1 { font-size: 18pt; color: #0A2342; text-align: center; margin: 0 0 8pt; }
  h2 { font-size: 13pt; color: #0A2342; border-bottom: 1.5pt solid #1565C0; padding-bottom: 3pt; margin: 14pt 0 6pt; }
  h3 { font-size: 11.5pt; color: #1565C0; margin: 10pt 0 4pt; }
  h4 { font-size: 10.5pt; margin: 8pt 0 3pt; }
  p, li { line-height: 1.55; margin: 4pt 0; }
  ul, ol { padding-left: 18pt; }
  table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9.5pt; }
  th { background: #0A2342; color: #fff; padding: 6pt 8pt; text-align: left; font-weight: 600; }
  td { padding: 5pt 8pt; border-bottom: 0.5pt solid #D0D9E4; }
  tr:nth-child(even) td { background: #F4F7FB; }
  hr { border: none; border-top: 1pt solid #D0D9E4; margin: 10pt 0; }
  strong { color: #0A2342; }
  @media print { body { padding: 15mm 20mm; } }
</style>
</head>
<body>${content}</body>
</html>`);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 500);
}

async function saveToProject() {
  if (!valGeneratedText || !window.activeProject) return;

  const btn = document.getElementById("btn-save-doc");
  if (btn) { btn.disabled = true; btn.textContent = "Saving…"; }

  const cfg     = window.VALIDATION_DOCS[valDocType] || {};
  const details = valFormData.details || {};
  const eqName  = valFormData.equipment_name || "Equipment";
  const proto   = details.protocol_number || details.doc_number || details.capa_number || details.deviation_number || valDocType;
  const title   = `${eqName} — ${cfg.short || valDocType} ${proto}`;

  try {
    const res = await fetch("/validation/save", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: window.activeProject.id,
        doc_type:   valDocType,
        title:      title,
        form_data:  valFormData,
        content:    valGeneratedText,
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    if (btn) { btn.textContent = "✓ Saved"; btn.style.background = "#2E7D32"; }
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "💾 Save to Project"; }
    alert(`Save failed: ${err.message}`);
  }
}

function backToWizard() {
  document.getElementById("val-wizard").style.display = "flex";
  document.getElementById("val-viewer").style.display = "none";
  _renderStep(4);   // return to Step 4 so user can click Generate again
}

// ── Utility ───────────────────────────────────────────────────────────────────

function escapeHtmlVal(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return String(str || "").replace(/"/g, "&quot;");
}

// Expose for index.html inline navigation script
window.openValidationWizard = openValidationWizard;
window.valNext              = valNext;
window.valBack              = valBack;
window.startGeneration      = startGeneration;
window.exportDocx           = exportDocx;
window.printDocument        = printDocument;
window.saveToProject        = saveToProject;
window.backToWizard         = backToWizard;
window._valToggleDoc        = _valToggleDoc;
window._valSelectAll        = _valSelectAll;
