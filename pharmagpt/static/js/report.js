/**
 * report.js — Validation Report Management Suite Frontend
 * The Lean Architect Technologies | PharmaGPT
 */

/* ── State ───────────────────────────────────────────────────────────────────── */

const ReportState = {
  currentReportId: null,
  currentReport: null,
  currentTab: 'overview',
  sections: [],
  currentSection: null,
  sectionMode: 'edit',   // 'edit' | 'preview'
  generating: false,
  generatingSection: null,
  qualList: [],
  ursList: [],
  riskList: [],
  wizardStep: 1,
  filters: {},
};

/* ── Section metadata (order / label) ────────────────────────────────────────── */

const REPORT_SECTIONS_META = [
  { key: 'cover_page',            label: 'Cover Page',                   order: 1 },
  { key: 'approval_page',         label: 'Approval Page',                order: 2 },
  { key: 'revision_history',      label: 'Revision History',             order: 3 },
  { key: 'executive_summary',     label: 'Executive Summary',            order: 5 },
  { key: 'purpose',               label: 'Purpose',                      order: 6 },
  { key: 'scope',                 label: 'Scope',                        order: 7 },
  { key: 'responsibilities',      label: 'Responsibilities',             order: 8 },
  { key: 'applicable_standards',  label: 'Applicable Standards',         order: 9 },
  { key: 'equipment_details',     label: 'Equipment Details',            order: 10 },
  { key: 'system_description',    label: 'System Description',           order: 11 },
  { key: 'validation_strategy',   label: 'Validation Strategy',          order: 12 },
  { key: 'urs_summary',           label: 'URS Summary',                  order: 13 },
  { key: 'risk_assessment_summary', label: 'Risk Assessment Summary',    order: 14 },
  { key: 'iq_summary',            label: 'IQ Summary',                   order: 15 },
  { key: 'oq_summary',            label: 'OQ Summary',                   order: 16 },
  { key: 'pq_summary',            label: 'PQ Summary',                   order: 17 },
  { key: 'execution_summary',     label: 'Execution Summary',            order: 18 },
  { key: 'deviation_summary',     label: 'Deviation Summary',            order: 19 },
  { key: 'traceability_summary',  label: 'Traceability Summary',         order: 20 },
  { key: 'critical_findings',     label: 'Critical Findings',            order: 21 },
  { key: 'risk_evaluation',       label: 'Risk Evaluation',              order: 22 },
  { key: 'compliance_assessment', label: 'Compliance Assessment',        order: 23 },
  { key: 'conclusion',            label: 'Conclusion',                   order: 24 },
  { key: 'recommendations',       label: 'Recommendations',              order: 25 },
  { key: 'final_statement',       label: 'Final Validation Statement',   order: 26 },
  { key: 'annexures',             label: 'Annexures',                    order: 27 },
  { key: 'supporting_evidence',   label: 'Supporting Evidence',          order: 28 },
];

/* ── Init ────────────────────────────────────────────────────────────────────── */

window.initReport = function () {
  showView('view-report');
  reportShowDashboard();
};

function showView(id) {
  document.querySelectorAll('main').forEach(m => m.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}

/* ── View switching ──────────────────────────────────────────────────────────── */

function reportShowView(viewId) {
  document.querySelectorAll('.report-view').forEach(v => v.classList.remove('active'));
  const el = document.getElementById(viewId);
  if (el) el.classList.add('active');
}

window.reportShowDashboard = function () {
  reportShowView('report-view-dashboard');
  loadReportDashboard();
};

window.reportShowList = function () {
  reportShowView('report-view-list');
  loadReportList();
};

window.reportShowNew = function () {
  reportShowView('report-view-new');
  initNewReportWizard();
};

/* ── API helpers ─────────────────────────────────────────────────────────────── */

async function rApi(path, opts = {}) {
  const r = await fetch('/report' + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) {
    let err;
    try { err = (await r.json()).error; } catch { err = r.statusText; }
    throw new Error(err || `HTTP ${r.status}`);
  }
  return r.json();
}

/* ── Dashboard ───────────────────────────────────────────────────────────────── */

async function loadReportDashboard() {
  const el = document.getElementById('report-dash-body');
  if (!el) return;
  el.innerHTML = '<div style="padding:40px;text-align:center;color:#66615B"><div class="report-spinner"></div></div>';
  try {
    const d = await rApi('/dashboard');
    el.innerHTML = renderReportDashboard(d);
  } catch (e) {
    el.innerHTML = `<div class="report-empty"><div class="report-empty-icon"><span class=\'icon\' data-lucide=\'alert-triangle\'></span></div><div class="report-empty-title">${e.message}</div></div>`;
  }
}

function renderReportDashboard(d) {
  const scoreColor = s => s >= 80 ? 'score-high' : s >= 60 ? 'score-medium' : 'score-low';

  return `
  <div class="report-inner">
    <div class="report-stats-grid">
      <div class="report-stat-card stat-total">
        <div class="report-stat-icon"><span class=\'icon\' data-lucide=\'clipboard-list\'></span></div>
        <div class="report-stat-value">${d.total}</div>
        <div class="report-stat-label">Total Reports</div>
      </div>
      <div class="report-stat-card stat-draft">
        <div class="report-stat-icon"><span class=\'icon\' data-lucide=\'pencil-line\'></span></div>
        <div class="report-stat-value">${d.draft}</div>
        <div class="report-stat-label">Draft</div>
      </div>
      <div class="report-stat-card stat-review">
        <div class="report-stat-icon"><span class=\'icon\' data-lucide=\'search\'></span></div>
        <div class="report-stat-value">${d.under_review}</div>
        <div class="report-stat-label">Under Review</div>
      </div>
      <div class="report-stat-card stat-approved">
        <div class="report-stat-icon"><span class=\'icon\' data-lucide=\'check-circle-2\'></span></div>
        <div class="report-stat-value">${d.approved}</div>
        <div class="report-stat-label">Approved</div>
      </div>
      <div class="report-stat-card stat-score">
        <div class="report-stat-icon"><span class=\'icon\' data-lucide=\'bot\'></span></div>
        <div class="report-stat-value">${d.ai_generated}</div>
        <div class="report-stat-label">AI Generated</div>
      </div>
      <div class="report-stat-card stat-score">
        <div class="report-stat-icon"><span class=\'icon\' data-lucide=\'package\'></span></div>
        <div class="report-stat-value">${d.released + d.archived}</div>
        <div class="report-stat-label">Released / Archived</div>
      </div>
    </div>

    <!-- Score cards -->
    <div class="report-stats-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:24px">
      <div class="report-stat-card">
        <div class="report-stat-label">Avg Compliance Score</div>
        <div class="report-stat-value ${scoreColor(d.avg_compliance)}" style="font-size:22px">${d.avg_compliance}%</div>
        <div class="report-score-bar-wrap">
          <div class="report-score-bar-bg"><div class="report-score-bar-fill" style="width:${d.avg_compliance}%"></div></div>
        </div>
      </div>
      <div class="report-stat-card">
        <div class="report-stat-label">Avg Completeness Score</div>
        <div class="report-stat-value ${scoreColor(d.avg_completeness)}" style="font-size:22px">${d.avg_completeness}%</div>
        <div class="report-score-bar-wrap">
          <div class="report-score-bar-bg"><div class="report-score-bar-fill" style="width:${d.avg_completeness}%"></div></div>
        </div>
      </div>
      <div class="report-stat-card">
        <div class="report-stat-label">Avg AI Readiness Score</div>
        <div class="report-stat-value ${scoreColor(d.avg_readiness)}" style="font-size:22px">${d.avg_readiness}%</div>
        <div class="report-score-bar-wrap">
          <div class="report-score-bar-bg"><div class="report-score-bar-fill" style="width:${d.avg_readiness}%"></div></div>
        </div>
      </div>
    </div>

    <div class="report-dash-grid">
      <!-- Recent reports -->
      <div class="report-panel">
        <div class="report-panel-header">
          <div class="report-panel-title">Recent Reports</div>
          <button class="report-btn report-btn-sm report-btn-outline" onclick="reportShowList()">View All</button>
        </div>
        <div class="report-panel-body" style="padding:0">
          ${d.recent.length === 0
            ? '<div class="report-empty" style="padding:30px"><div class="report-empty-icon"><span class=\'icon\' data-lucide=\'clipboard-list\'></span></div><div>No reports yet</div></div>'
            : `<table class="report-list-table">
                <thead><tr>
                  <th>Report #</th><th>Equipment</th><th>Department</th>
                  <th>Status</th><th>AI Score</th>
                </tr></thead>
                <tbody>
                  ${d.recent.map(r => `
                  <tr onclick="openReport(${r.id})">
                    <td><strong style="color:#2D2A28">${r.report_number || '—'}</strong></td>
                    <td>${r.equipment_name || r.title || '—'}</td>
                    <td>${r.department || '—'}</td>
                    <td><span class="report-badge badge-${r.status}">${r.status}</span></td>
                    <td>
                      <div class="progress-mini">
                        <div class="progress-mini-bar"><div class="progress-mini-fill" style="width:${r.ai_readiness_score}%"></div></div>
                        <span class="progress-mini-val">${r.ai_readiness_score}%</span>
                      </div>
                    </td>
                  </tr>`).join('')}
                </tbody>
              </table>`
          }
        </div>
      </div>

      <!-- Right column -->
      <div>
        <!-- By Department -->
        ${d.by_department.length ? `
        <div class="report-panel" style="margin-bottom:16px">
          <div class="report-panel-header"><div class="report-panel-title">By Department</div></div>
          <div class="report-panel-body">
            ${d.by_department.map(r => `
            <div style="display:flex;justify-content:space-between;padding:5px 0;font-size:13px">
              <span style="color:#9A948C">${r.department}</span>
              <span style="color:#8A6B52;font-weight:700">${r.cnt}</span>
            </div>`).join('')}
          </div>
        </div>` : ''}

        <!-- Status breakdown -->
        <div class="report-panel">
          <div class="report-panel-header"><div class="report-panel-title">Status Breakdown</div></div>
          <div class="report-panel-body">
            ${d.by_status.map(r => {
              const pct = d.total > 0 ? Math.round(r.cnt / d.total * 100) : 0;
              return `<div style="margin-bottom:10px">
                <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px">
                  <span style="color:#9A948C;text-transform:capitalize">${r.status.replace('_',' ')}</span>
                  <span style="color:#66615B">${r.cnt} (${pct}%)</span>
                </div>
                <div class="report-score-bar-bg"><div class="report-score-bar-fill" style="width:${pct}%"></div></div>
              </div>`;
            }).join('')}
          </div>
        </div>
      </div>
    </div>
  </div>`;
}

/* ── List View ───────────────────────────────────────────────────────────────── */

async function loadReportList() {
  const body = document.getElementById('report-list-body');
  if (!body) return;
  body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:#66615B"><div class="report-spinner"></div></td></tr>';

  const q = new URLSearchParams({
    status: ReportState.filters.status || '',
    q: ReportState.filters.keyword || '',
    department: ReportState.filters.department || '',
  }).toString();

  try {
    const reports = await rApi('/?' + q);
    if (!reports.length) {
      body.innerHTML = '<tr><td colspan="8"><div class="report-empty"><div class="report-empty-icon"><span class=\'icon\' data-lucide=\'clipboard-list\'></span></div><div class="report-empty-title">No reports found</div><div class="report-empty-sub">Create your first validation report to get started</div><button class="report-btn report-btn-primary" onclick="reportShowNew()">+ New Report</button></div></td></tr>';
      return;
    }
    body.innerHTML = reports.map(r => `
      <tr onclick="openReport(${r.id})">
        <td><strong style="color:#2D2A28">${r.report_number || '—'}</strong></td>
        <td>
          <div style="font-weight:600;color:#2D2A28">${r.title}</div>
          <div style="font-size:11px;color:#66615B">${r.equipment_name || ''}</div>
        </td>
        <td>${r.department || '—'}</td>
        <td><span class="report-badge badge-${r.status}">${r.status.replace('_',' ')}</span></td>
        <td>${r.validation_type || '—'}</td>
        <td>
          <div class="progress-mini">
            <div class="progress-mini-bar"><div class="progress-mini-fill" style="width:${r.completeness_score}%"></div></div>
            <span class="progress-mini-val">${r.completeness_score}%</span>
          </div>
        </td>
        <td>
          <span style="font-size:13px;font-weight:700;${r.ai_readiness_score>=80?'color:#5F8A61':r.ai_readiness_score>=60?'color:#C59A41':'color:#CE7975'}">
            ${r.ai_readiness_score || 0}%
          </span>
        </td>
        <td style="font-size:11px;color:#66615B">${(r.created_at||'').slice(0,10)}</td>
      </tr>`).join('');
  } catch (e) {
    body.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:30px;color:#CE7975">${e.message}</td></tr>`;
  }
}

/* ── New Report Wizard ───────────────────────────────────────────────────────── */

async function initNewReportWizard() {
  ReportState.wizardStep = 1;
  // Load available quals, URS, risk assessments for linking
  try {
    const [quals, urs, risks] = await Promise.all([
      fetch('/qual/').then(r => r.json()),
      fetch('/urs/').then(r => r.json()),
      fetch('/risk/assessments/').then(r => r.json()),
    ]);
    ReportState.qualList = quals || [];
    ReportState.ursList  = urs  || [];
    ReportState.riskList = risks || [];
  } catch { }
  renderNewReportWizard();
}

function renderNewReportWizard() {
  const el = document.getElementById('report-new-body');
  if (!el) return;

  const quals = ReportState.qualList;
  const ursList = ReportState.ursList;
  const riskList = ReportState.riskList;

  el.innerHTML = `
  <div class="report-inner" style="max-width:860px">
    <div class="report-wizard-steps">
      ${[['1','Link Modules'],['2','Report Details'],['3','Create']].map(([n,l],i) => `
        <div class="report-wizard-step ${ReportState.wizardStep == n ? 'active' : ReportState.wizardStep > n ? 'done' : ''}" onclick="reportWizardStep(${n})">
          <div class="report-wizard-step-num">${ReportState.wizardStep > n ? '<span class=\'icon\' data-lucide=\'check\'></span>' : n}</div>
          ${l}
        </div>`).join('')}
    </div>

    <!-- Step 1: Link Modules -->
    <div class="report-wizard-panel ${ReportState.wizardStep === 1 ? 'active' : ''}" id="rwiz-1">
      <h3 style="color:#2D2A28;margin-bottom:6px">Link to Completed Qualification</h3>
      <p style="color:#66615B;font-size:13px;margin-bottom:18px">
        Select a qualification project to automatically populate the report with IQ/OQ/PQ data.
      </p>

      <div style="margin-bottom:20px">
        <div style="font-size:12px;font-weight:700;color:#66615B;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px">
          Qualification Project (IQ/OQ/PQ)
        </div>
        ${quals.length === 0
          ? '<div style="color:#66615B;font-size:13px;padding:14px;background:#FFFFFF;border-radius:8px;border:1px solid #E6DED6">No qualification projects found. You can still create a standalone report.</div>'
          : `<div style="display:grid;gap:8px;max-height:280px;overflow-y:auto">
              ${quals.map(q => `
              <div class="report-link-card ${document.getElementById('rwiz-qual-id') && document.getElementById('rwiz-qual-id').value == q.id ? 'selected' : ''}"
                   onclick="selectLinkedQual(${q.id},'${esc(q.title)}','${esc(q.equipment_name)}')">
                <div class="report-link-card-title">${q.qual_number || 'QUAL-'+q.id}</div>
                <div class="report-link-card-value">${q.title}</div>
                <div class="report-link-card-sub">${q.equipment_name} | ${q.department} | IQ:${q.iq_status} OQ:${q.oq_status} PQ:${q.pq_status}</div>
              </div>`).join('')}
            </div>`
        }
        <input type="hidden" id="rwiz-qual-id" value="">
      </div>

      <div class="report-form-grid" style="grid-template-columns:1fr 1fr;margin-top:16px">
        <div>
          <div style="font-size:12px;font-weight:700;color:#66615B;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Link URS (optional)</div>
          <select class="report-filter-select" id="rwiz-urs-id" style="width:100%">
            <option value="">— Select URS —</option>
            ${ursList.map(u => `<option value="${u.id}">${u.urs_number || 'URS-'+u.id} — ${u.title.slice(0,40)}</option>`).join('')}
          </select>
        </div>
        <div>
          <div style="font-size:12px;font-weight:700;color:#66615B;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Link Risk Assessment (optional)</div>
          <select class="report-filter-select" id="rwiz-risk-id" style="width:100%">
            <option value="">— Select Risk Assessment —</option>
            ${riskList.map(r => `<option value="${r.id}">${r.title.slice(0,40)}</option>`).join('')}
          </select>
        </div>
      </div>

      <div style="margin-top:24px;display:flex;justify-content:flex-end">
        <button class="report-btn report-btn-primary" onclick="reportWizardStep(2)">Next: Report Details <span class=\'icon\' data-lucide=\'arrow-right\'></span></button>
      </div>
    </div>

    <!-- Step 2: Report Details -->
    <div class="report-wizard-panel ${ReportState.wizardStep === 2 ? 'active' : ''}" id="rwiz-2">
      <h3 style="color:#2D2A28;margin-bottom:6px">Report Details</h3>
      <p style="color:#66615B;font-size:13px;margin-bottom:18px">Enter the report metadata. Fields will be pre-filled from the linked qualification.</p>

      <div class="report-form-grid">
        <div class="report-field">
          <label>Report Number *</label>
          <input type="text" id="rwiz-report-number" placeholder="e.g. VR-2025-001">
        </div>
        <div class="report-field">
          <label>Report Type</label>
          <select id="rwiz-report-type">
            <option>Validation Report</option>
            <option>Re-qualification Report</option>
            <option>Periodic Review Report</option>
            <option>Cleaning Validation Report</option>
            <option>Process Validation Report</option>
            <option>Computer System Validation Report</option>
          </select>
        </div>
        <div class="report-field">
          <label>Equipment Name *</label>
          <input type="text" id="rwiz-equipment-name" placeholder="Equipment name">
        </div>
        <div class="report-field">
          <label>Equipment ID</label>
          <input type="text" id="rwiz-equipment-id" placeholder="Asset tag / ID">
        </div>
        <div class="report-field">
          <label>Manufacturer</label>
          <input type="text" id="rwiz-manufacturer" placeholder="Manufacturer">
        </div>
        <div class="report-field">
          <label>Model</label>
          <input type="text" id="rwiz-model" placeholder="Model number">
        </div>
        <div class="report-field">
          <label>Department</label>
          <input type="text" id="rwiz-department" placeholder="Department">
        </div>
        <div class="report-field">
          <label>Site / Location</label>
          <input type="text" id="rwiz-location" placeholder="Site / Room">
        </div>
        <div class="report-field">
          <label>Validation Type</label>
          <select id="rwiz-val-type">
            <option>IQ/OQ/PQ</option>
            <option>IQ/OQ</option>
            <option>OQ/PQ</option>
            <option>IQ Only</option>
            <option>OQ Only</option>
            <option>PQ Only</option>
            <option>DQ/IQ/OQ/PQ</option>
          </select>
        </div>
        <div class="report-field">
          <label>Prepared By</label>
          <input type="text" id="rwiz-prepared-by" placeholder="Author name">
        </div>
        <div class="report-field">
          <label>Reviewed By</label>
          <input type="text" id="rwiz-reviewed-by" placeholder="Reviewer name">
        </div>
        <div class="report-field">
          <label>Report Date</label>
          <input type="date" id="rwiz-report-date" value="${new Date().toISOString().slice(0,10)}">
        </div>
        <div class="report-field report-form-full">
          <label>Scope</label>
          <textarea id="rwiz-scope" rows="3" placeholder="Define the scope of this validation report..."></textarea>
        </div>
      </div>

      <div style="margin-top:24px;display:flex;justify-content:space-between">
        <button class="report-btn report-btn-outline" onclick="reportWizardStep(1)"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
        <button class="report-btn report-btn-primary" onclick="reportWizardStep(3)">Next: Confirm <span class=\'icon\' data-lucide=\'arrow-right\'></span></button>
      </div>
    </div>

    <!-- Step 3: Create -->
    <div class="report-wizard-panel ${ReportState.wizardStep === 3 ? 'active' : ''}" id="rwiz-3">
      <h3 style="color:#2D2A28;margin-bottom:6px">Create Report</h3>
      <p style="color:#66615B;font-size:13px;margin-bottom:20px">Review your selections and create the validation report.</p>

      <div class="report-panel" style="margin-bottom:20px">
        <div class="report-panel-header"><div class="report-panel-title">Summary</div></div>
        <div class="report-panel-body" id="rwiz-summary">Loading...</div>
      </div>

      <div style="background:#FFFFFF;border:1px solid #E6DED6;border-radius:10px;padding:16px;margin-bottom:20px">
        <div style="font-size:12px;font-weight:700;color:#2D2A28;margin-bottom:8px"><span class=\'icon\' data-lucide=\'bot\'></span> AI Generation Options</div>
        <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-size:13px;color:#9A948C">
          <input type="checkbox" id="rwiz-auto-gen" checked style="width:16px;height:16px">
          Automatically generate all report sections with AI after creation
        </label>
      </div>

      <div style="margin-top:24px;display:flex;justify-content:space-between;align-items:center">
        <button class="report-btn report-btn-outline" onclick="reportWizardStep(2)"><span class=\'icon\' data-lucide=\'arrow-left\'></span> Back</button>
        <button class="report-btn report-btn-success" onclick="createNewReport()" id="btn-create-report">
          <span class=\'icon\' data-lucide=\'check\'></span> Create Validation Report
        </button>
      </div>
    </div>
  </div>`;
}

function reportWizardStep(n) {
  ReportState.wizardStep = n;
  if (n === 3) renderWizardSummary();
  renderNewReportWizard();
}

function selectLinkedQual(id, title, eqName) {
  document.getElementById('rwiz-qual-id').value = id;
  // Pre-fill equipment name if empty
  const eqInput = document.getElementById('rwiz-equipment-name');
  if (eqInput && !eqInput.value) eqInput.value = eqName;
  // Also try pre-fill URS/Risk from qual — would need API call; skip for now
  reportWizardStep(1); // re-render to show selection
}

function renderWizardSummary() {
  const el = document.getElementById('rwiz-summary');
  if (!el) return;
  const qualId = (document.getElementById('rwiz-qual-id') || {}).value;
  const qual = qualId ? ReportState.qualList.find(q => q.id == qualId) : null;
  const ursId = (document.getElementById('rwiz-urs-id') || {}).value;
  const urs = ursId ? ReportState.ursList.find(u => u.id == ursId) : null;
  const riskId = (document.getElementById('rwiz-risk-id') || {}).value;
  const risk = riskId ? ReportState.riskList.find(r => r.id == riskId) : null;

  el.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:13px">
      <div><span style="color:#66615B">Report #:</span> <strong style="color:#2D2A28">${v('rwiz-report-number')}</strong></div>
      <div><span style="color:#66615B">Type:</span> <strong style="color:#2D2A28">${v('rwiz-report-type')}</strong></div>
      <div><span style="color:#66615B">Equipment:</span> <strong style="color:#2D2A28">${v('rwiz-equipment-name')}</strong></div>
      <div><span style="color:#66615B">Department:</span> <strong style="color:#2D2A28">${v('rwiz-department')}</strong></div>
      <div><span style="color:#66615B">Prepared By:</span> <strong style="color:#2D2A28">${v('rwiz-prepared-by')}</strong></div>
      <div><span style="color:#66615B">Validation Type:</span> <strong style="color:#2D2A28">${v('rwiz-val-type')}</strong></div>
      <div><span style="color:#66615B">Linked Qual:</span> <strong style="color:#2D2A28">${qual ? qual.title.slice(0,40) : 'None'}</strong></div>
      <div><span style="color:#66615B">Linked URS:</span> <strong style="color:#2D2A28">${urs ? urs.title.slice(0,40) : 'None'}</strong></div>
      <div><span style="color:#66615B">Linked Risk:</span> <strong style="color:#2D2A28">${risk ? risk.title.slice(0,40) : 'None'}</strong></div>
    </div>`;
}

async function createNewReport() {
  const btn = document.getElementById('btn-create-report');
  btn.disabled = true;
  btn.textContent = 'Creating...';

  const payload = {
    report_number: v('rwiz-report-number'),
    report_type: v('rwiz-report-type'),
    equipment_name: v('rwiz-equipment-name'),
    equipment_id: v('rwiz-equipment-id'),
    manufacturer: v('rwiz-manufacturer'),
    model: v('rwiz-model'),
    department: v('rwiz-department'),
    location: v('rwiz-location'),
    validation_type: v('rwiz-val-type'),
    prepared_by: v('rwiz-prepared-by'),
    reviewed_by: v('rwiz-reviewed-by'),
    report_date: v('rwiz-report-date'),
    scope: v('rwiz-scope'),
    linked_qual_id: v('rwiz-qual-id') || null,
    linked_urs_id: v('rwiz-urs-id') || null,
    linked_risk_id: v('rwiz-risk-id') || null,
  };

  try {
    const report = await rApi('/', { method: 'POST', body: JSON.stringify(payload) });
    ReportState.currentReportId = report.id;
    ReportState.currentReport = report;
    showReportToast('Validation report created successfully', 'success');

    const autoGen = document.getElementById('rwiz-auto-gen');
    if (autoGen && autoGen.checked) {
      openReport(report.id, true);
    } else {
      openReport(report.id);
    }
  } catch (e) {
    showReportToast('Error: ' + e.message, 'error');
    btn.disabled = false;
 btn.textContent = ' Create Validation Report';
  }
}

/* ── Open / Detail View ──────────────────────────────────────────────────────── */

window.openReport = async function (id, autoGenerate = false) {
  try {
    const report = await rApi('/' + id);
    const sections = await rApi('/' + id + '/sections');
    ReportState.currentReportId = id;
    ReportState.currentReport = report;
    ReportState.sections = sections;
    ReportState.currentSection = REPORT_SECTIONS_META[0].key;
    ReportState.currentTab = 'overview';
    reportShowView('report-view-detail');
    renderReportDetail(report, sections);
    if (autoGenerate) {
      setTimeout(() => generateAllSections(), 800);
    }
  } catch (e) {
    showReportToast('Error loading report: ' + e.message, 'error');
  }
};

function renderReportDetail(report, sections) {
  const el = document.getElementById('report-detail-body');
  if (!el) return;

  const generatedCount = sections.filter(s => s.is_generated || (s.content && s.content.trim().length > 50)).length;
  const totalSections = sections.length;
  const completePct = Math.round(generatedCount / totalSections * 100);

  el.innerHTML = `
    <!-- Detail header -->
    <div class="report-detail-header">
      <div class="report-detail-meta">
        <div class="report-detail-title">${report.title}</div>
        <div class="report-detail-sub">${report.report_number || ''} ${report.report_number && report.equipment_name ? '·' : ''} ${report.equipment_name || ''} ${report.department ? '· ' + report.department : ''}</div>
        <div class="report-detail-badges">
          <span class="report-badge badge-${report.status}">${report.status.replace('_',' ')}</span>
          <span class="report-badge" style="background:#F1ECE6;color:#9A948C">Rev ${report.revision}</span>
          <span class="report-badge" style="background:#F1ECE6;color:#9A948C">${report.validation_type}</span>
          ${report.ai_generated ? '<span class="report-badge" style="background:#F1ECE6;color:#2D2A28"><span class=\'icon\' data-lucide=\'bot\'></span> AI Generated</span>' : ''}
        </div>
      </div>
      <div class="report-header-actions" style="flex-shrink:0">
        <button class="report-btn report-btn-sm report-btn-outline" onclick="reportShowList()"><span class=\'icon\' data-lucide=\'arrow-left\'></span> All Reports</button>
        <button class="report-btn report-btn-sm report-btn-primary" onclick="generateAllSections()" id="btn-gen-all" ${ReportState.generating ? 'disabled' : ''}>
          <span class=\'icon\' data-lucide=\'bot\'></span> Generate All
        </button>
        <button class="report-btn report-btn-sm report-btn-success" onclick="runAIReview()" id="btn-ai-review">
          <span class=\'icon\' data-lucide=\'search\'></span> AI Review
        </button>
        <button class="report-btn report-btn-sm report-btn-outline" onclick="exportReportDocx(${report.id})">
          <span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span> Export DOCX
        </button>
        <button class="report-btn report-btn-sm report-btn-warning" onclick="submitForApproval()">
          <span class=\'icon\' data-lucide=\'upload\'></span> Submit for Review
        </button>
      </div>
    </div>

    <!-- Completion bar -->
    <div style="padding:12px 28px;border-bottom:1px solid #E6DED6;display:flex;align-items:center;gap:16px">
      <div style="font-size:12px;color:#66615B">Sections: ${generatedCount}/${totalSections}</div>
      <div style="flex:1;max-width:300px">
        <div class="report-score-bar-bg" style="height:8px">
          <div class="report-score-bar-fill" style="width:${completePct}%"></div>
        </div>
      </div>
      <div style="font-size:12px;color:#8A6B52;font-weight:700">${completePct}% Complete</div>
      ${report.compliance_score ? `<div style="font-size:12px;color:#5F8A61;font-weight:700">Compliance: ${report.compliance_score}%</div>` : ''}
      ${report.ai_readiness_score ? `<div style="font-size:12px;color:#C59A41;font-weight:700">Readiness: ${report.ai_readiness_score}%</div>` : ''}
    </div>

    <!-- Tabs -->
    <div class="report-tabs">
      ${[
        ['overview',     'Overview'],
        ['sections',     'Report Sections'],
        ['traceability', 'Traceability'],
        ['ai-review',    'AI Review'],
        ['approval',     'Approval & Workflow'],
        ['versions',     'Version History'],
      ].map(([k,l]) => `<div class="report-tab ${ReportState.currentTab===k?'active':''}" onclick="switchReportTab('${k}')">${l}</div>`).join('')}
    </div>

    <!-- Tab panels -->
    <div class="report-tab-panel ${ReportState.currentTab==='overview'?'active':''}" id="rtab-overview">
      ${renderOverviewTab(report, sections)}
    </div>
    <div class="report-tab-panel ${ReportState.currentTab==='sections'?'active':''}" id="rtab-sections">
      ${renderSectionsTab(report, sections)}
    </div>
    <div class="report-tab-panel ${ReportState.currentTab==='traceability'?'active':''}" id="rtab-traceability">
      <div id="trace-content">
        <div style="text-align:center;padding:40px;color:#66615B">
          <button class="report-btn report-btn-primary" onclick="loadTraceability()">Load Traceability Matrix</button>
        </div>
      </div>
    </div>
    <div class="report-tab-panel ${ReportState.currentTab==='ai-review'?'active':''}" id="rtab-ai-review">
      <div id="review-content">
        ${report.compliance_score > 0 ? '' : '<div style="text-align:center;padding:40px;color:#66615B"><button class="report-btn report-btn-success" onclick="runAIReview()"><span class=\'icon\' data-lucide=\'search\'></span> Run AI Review</button></div>'}
      </div>
    </div>
    <div class="report-tab-panel ${ReportState.currentTab==='approval'?'active':''}" id="rtab-approval">
      <div id="approval-content"><div style="text-align:center;padding:20px"><div class="report-spinner"></div></div></div>
    </div>
    <div class="report-tab-panel ${ReportState.currentTab==='versions'?'active':''}" id="rtab-versions">
      <div id="versions-content"><div style="text-align:center;padding:20px"><div class="report-spinner"></div></div></div>
    </div>
  `;

  // Auto-load approval & versions
  loadApprovalTrail();
  loadVersionHistory();
}

function renderOverviewTab(report, sections) {
  const stats = [
    ['Equipment', report.equipment_name || '—'],
    ['Equipment ID', report.equipment_id || '—'],
    ['Manufacturer', report.manufacturer || '—'],
    ['Model', report.model || '—'],
    ['Serial No.', report.serial_number || '—'],
    ['Department', report.department || '—'],
    ['Site', report.site || '—'],
    ['Location', report.location || '—'],
    ['Validation Type', report.validation_type || '—'],
    ['Prepared By', report.prepared_by || '—'],
    ['Reviewed By', report.reviewed_by || '—'],
    ['Approved By', report.approved_by || '—'],
    ['Report Date', report.report_date || '—'],
    ['Status', report.status || '—'],
    ['Revision', report.revision || 'A'],
    ['Total Tests', report.total_tests || 0],
    ['Passed', report.pass_count || 0],
    ['Failed', report.fail_count || 0],
    ['Deviations', report.deviation_count || 0],
  ];

  return `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div class="report-panel">
        <div class="report-panel-header"><div class="report-panel-title">Report Information</div></div>
        <div class="report-panel-body">
          <table style="width:100%;border-collapse:collapse;font-size:13px">
            ${stats.slice(0,9).map(([k,v]) => `
            <tr>
              <td style="padding:6px 0;color:#66615B;width:45%">${k}</td>
              <td style="padding:6px 0;color:#2D2A28;font-weight:500">${v}</td>
            </tr>`).join('')}
          </table>
        </div>
      </div>
      <div>
        <div class="report-panel" style="margin-bottom:16px">
          <div class="report-panel-header"><div class="report-panel-title">Execution Data</div></div>
          <div class="report-panel-body">
            <table style="width:100%;border-collapse:collapse;font-size:13px">
              ${stats.slice(9).map(([k,v]) => `
              <tr>
                <td style="padding:6px 0;color:#66615B;width:50%">${k}</td>
                <td style="padding:6px 0;color:#2D2A28;font-weight:500">${v}</td>
              </tr>`).join('')}
            </table>
          </div>
        </div>
        <div class="report-panel">
          <div class="report-panel-header"><div class="report-panel-title">Quick Actions</div></div>
          <div class="report-panel-body" style="display:flex;flex-direction:column;gap:8px">
            <button class="report-btn report-btn-primary" onclick="switchReportTab('sections');generateAllSections()"><span class=\'icon\' data-lucide=\'bot\'></span> AI Generate All Sections</button>
            <button class="report-btn report-btn-success" onclick="runAIReview()"><span class=\'icon\' data-lucide=\'search\'></span> Run AI Review</button>
            <button class="report-btn report-btn-outline" onclick="switchReportTab('traceability');loadTraceability()"><span class=\'icon\' data-lucide=\'link-2\'></span> Build Traceability Matrix</button>
            <button class="report-btn report-btn-outline" onclick="exportReportDocx(${report.id})"><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span> Export as DOCX</button>
            <button class="report-btn report-btn-warning" onclick="submitForApproval()"><span class=\'icon\' data-lucide=\'upload\'></span> Submit for QA Review</button>
          </div>
        </div>
      </div>
    </div>`;
}

function renderSectionsTab(report, sections) {
  const sectionMap = {};
  sections.forEach(s => { sectionMap[s.section_key] = s; });

  const orderedSections = REPORT_SECTIONS_META.map(m => ({
    ...m,
    ...(sectionMap[m.key] || {}),
  }));

  return `
    <div>
      <!-- Generation controls -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px;flex-wrap:wrap">
        <div style="display:flex;gap:8px">
          <button class="report-btn report-btn-sm report-btn-primary" onclick="generateAllSections()" id="btn-gen-all-sec"><span class=\'icon\' data-lucide=\'bot\'></span> Generate All Sections</button>
          <div class="report-toggle-view" id="section-view-toggle">
            <button class="${ReportState.sectionMode==='edit'?'active':''}" onclick="setSectionMode('edit')"><span class=\'icon\' data-lucide=\'pencil\'></span> Edit</button>
            <button class="${ReportState.sectionMode==='preview'?'active':''}" onclick="setSectionMode('preview')"><span class=\'icon\' data-lucide=\'eye\'></span> Preview</button>
          </div>
        </div>
        <div style="font-size:12px;color:#66615B">
          ${sections.filter(s => s.is_generated).length} / ${sections.length} sections generated
        </div>
      </div>

      <!-- Generation progress (hidden by default) -->
      <div class="report-gen-progress" id="gen-progress-block" style="display:none">
        <div class="report-gen-progress-title"><div class="report-spinner"></div> Generating Report Sections...</div>
        <div class="report-gen-progress-list" id="gen-progress-list"></div>
        <div class="report-gen-overall">
          <div class="report-gen-overall-label">Overall Progress</div>
          <div class="report-gen-overall-bar"><div class="report-gen-overall-fill" id="gen-progress-fill" style="width:0%"></div></div>
        </div>
      </div>

      <!-- Sections grid -->
      <div class="report-sections-grid section-${ReportState.sectionMode}-mode" id="sections-grid">
        <!-- Left nav -->
        <div class="report-sections-nav" id="sections-nav">
          ${orderedSections.map((s, i) => {
            const dbSection = sectionMap[s.key];
            const hasContent = dbSection && dbSection.content && dbSection.content.trim().length > 50;
            return `
            <div class="report-section-nav-item ${s.key === ReportState.currentSection ? 'active' : ''} ${hasContent ? 'generated' : ''}"
                 onclick="selectSection('${s.key}')" id="snav-${s.key}">
              <div class="section-status-dot"></div>
              <span class="report-section-nav-number">${i+1}</span>
              <span style="flex:1;font-size:12px">${s.label}</span>
              ${hasContent ? '<span style="font-size:10px"><span class=\'icon\' data-lucide=\'check\'></span></span>' : ''}
            </div>`;
          }).join('')}
        </div>

        <!-- Editor -->
        <div class="report-section-editor" id="section-editor">
          <div class="report-section-editor-header">
            <div class="report-section-editor-title" id="section-editor-title">Select a section</div>
            <div style="display:flex;gap:8px">
              <button class="report-btn report-btn-sm report-btn-primary" onclick="generateCurrentSection()" id="btn-gen-section"><span class=\'icon\' data-lucide=\'bot\'></span> Generate</button>
              <button class="report-btn report-btn-sm report-btn-outline" onclick="saveSectionContent()" id="btn-save-section"><span class=\'icon\' data-lucide=\'save\'></span> Save</button>
            </div>
          </div>
          <div class="report-section-editor-body">
            <textarea class="report-section-textarea" id="section-textarea" placeholder="Select a section from the left panel, then click Generate to AI-generate it or type directly..."></textarea>
            <div class="report-section-preview" id="section-preview"></div>
          </div>
        </div>
      </div>
    </div>`;
}

/* ── Section interaction ─────────────────────────────────────────────────────── */

window.selectSection = function (key) {
  ReportState.currentSection = key;

  // Update nav
  document.querySelectorAll('.report-section-nav-item').forEach(el => el.classList.remove('active'));
  const navEl = document.getElementById('snav-' + key);
  if (navEl) navEl.classList.add('active');

  const meta = REPORT_SECTIONS_META.find(m => m.key === key);
  const section = ReportState.sections.find(s => s.section_key === key);

  const titleEl = document.getElementById('section-editor-title');
  if (titleEl) titleEl.textContent = meta ? meta.label : key;

  const textarea = document.getElementById('section-textarea');
  const preview = document.getElementById('section-preview');
  if (textarea) textarea.value = section ? (section.content || '') : '';
  if (preview && typeof marked !== 'undefined') {
    preview.innerHTML = marked.parse(section ? (section.content || '') : '');
  }
};

window.setSectionMode = function (mode) {
  ReportState.sectionMode = mode;
  const grid = document.getElementById('sections-grid');
  if (grid) {
    grid.className = grid.className.replace(/section-\w+-mode/g, '') + ' section-' + mode + '-mode';
  }
  document.querySelectorAll('#section-view-toggle button').forEach((b, i) => {
    b.classList.toggle('active', (i === 0 && mode === 'edit') || (i === 1 && mode === 'preview'));
  });
};

window.saveSectionContent = async function () {
  if (!ReportState.currentSection || !ReportState.currentReportId) return;
  const content = (document.getElementById('section-textarea') || {}).value || '';
  try {
    const updated = await rApi(`/${ReportState.currentReportId}/sections/${ReportState.currentSection}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
    // Update local state
    const idx = ReportState.sections.findIndex(s => s.section_key === ReportState.currentSection);
    if (idx >= 0) ReportState.sections[idx] = updated;
    // Update nav dot
    const navEl = document.getElementById('snav-' + ReportState.currentSection);
    if (navEl && content.trim().length > 50) navEl.classList.add('generated');
    showReportToast('Section saved', 'success');
  } catch (e) {
    showReportToast('Error saving: ' + e.message, 'error');
  }
};

/* ── AI Generation ───────────────────────────────────────────────────────────── */

window.generateCurrentSection = function () {
  if (!ReportState.currentSection || !ReportState.currentReportId || ReportState.generating) return;
  const key = ReportState.currentSection;

  const textarea = document.getElementById('section-textarea');
  if (textarea) textarea.value = '';

  const btn = document.getElementById('btn-gen-section');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Generating...'; }
  ReportState.generating = true;

  const es = new EventSource(`/report/${ReportState.currentReportId}/generate/${key}`);
  let accumulated = '';

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.chunk) {
      accumulated += data.chunk;
      if (textarea) textarea.value = accumulated;
    }
    if (data.done || data.error) {
      es.close();
      ReportState.generating = false;
 if (btn) { btn.disabled = false; btn.textContent = ' Generate'; }
      if (data.error) {
        showReportToast('Generation error: ' + data.error, 'error');
        return;
      }
      // Update local section state
      const idx = ReportState.sections.findIndex(s => s.section_key === key);
      if (idx >= 0) {
        ReportState.sections[idx].content = accumulated;
        ReportState.sections[idx].is_generated = 1;
      }
      const navEl = document.getElementById('snav-' + key);
      if (navEl) navEl.classList.add('generated');
      const preview = document.getElementById('section-preview');
      if (preview && typeof marked !== 'undefined') preview.innerHTML = marked.parse(accumulated);
      showReportToast('Section generated successfully', 'success');
    }
  };

  es.onerror = () => {
    es.close();
    ReportState.generating = false;
 if (btn) { btn.disabled = false; btn.textContent = ' Generate'; }
    showReportToast('Stream error', 'error');
  };
};

window.generateAllSections = function () {
  if (!ReportState.currentReportId || ReportState.generating) return;
  ReportState.generating = true;

  const progressBlock = document.getElementById('gen-progress-block');
  const progressList = document.getElementById('gen-progress-list');
  const progressFill = document.getElementById('gen-progress-fill');

  if (progressBlock) progressBlock.style.display = 'block';

  // Set up all sections in progress list
  const sectionKeys = REPORT_SECTIONS_META.map(m => m.key).filter(k => !['annexures','supporting_evidence','table_of_contents'].includes(k));

  if (progressList) {
    progressList.innerHTML = sectionKeys.map(k => {
      const meta = REPORT_SECTIONS_META.find(m => m.key === k);
      return `<div class="report-gen-progress-item" id="pitem-${k}">
        <div class="dot"></div>
        <span>${meta ? meta.label : k}</span>
      </div>`;
    }).join('');
  }

  // Switch to sections tab to show progress
  switchReportTab('sections');

  const btnAll = document.getElementById('btn-gen-all');
  const btnAllSec = document.getElementById('btn-gen-all-sec');
  if (btnAll) { btnAll.disabled = true; btnAll.innerHTML = '<div class="report-spinner"></div> Generating...'; }
  if (btnAllSec) { btnAllSec.disabled = true; btnAllSec.innerHTML = '<div class="report-spinner"></div> Generating...'; }

  let doneCount = 0;
  let currentSectionKey = null;
  let currentAccumulated = '';

  const es = new EventSource(`/report/${ReportState.currentReportId}/generate`);

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);

    if (data.status === 'generating') {
      currentSectionKey = data.section;
      currentAccumulated = '';
      // Mark as active
      const pitem = document.getElementById('pitem-' + data.section);
      if (pitem) pitem.className = 'report-gen-progress-item active';

      // Scroll nav to section and select it
      ReportState.currentSection = data.section;
      const navEl = document.getElementById('snav-' + data.section);
      if (navEl) {
        document.querySelectorAll('.report-section-nav-item').forEach(n => n.classList.remove('active'));
        navEl.classList.add('active');
        navEl.scrollIntoView({ block: 'nearest' });
      }
      const titleEl = document.getElementById('section-editor-title');
      const meta = REPORT_SECTIONS_META.find(m => m.key === data.section);
      if (titleEl) titleEl.textContent = meta ? meta.label : data.section;

      const textarea = document.getElementById('section-textarea');
      if (textarea) textarea.value = '';
    }

    if (data.chunk) {
      currentAccumulated += data.chunk;
      const textarea = document.getElementById('section-textarea');
      if (textarea) textarea.value = currentAccumulated;
    }

    if (data.section_done) {
      doneCount++;
      const pitem = document.getElementById('pitem-' + data.section);
      if (pitem) pitem.className = 'report-gen-progress-item done';
      if (progressFill) progressFill.style.width = Math.round(doneCount / sectionKeys.length * 100) + '%';

      // Update local state
      const idx = ReportState.sections.findIndex(s => s.section_key === data.section);
      if (idx >= 0) {
        ReportState.sections[idx].content = currentAccumulated;
        ReportState.sections[idx].is_generated = 1;
      }
      const navEl = document.getElementById('snav-' + data.section);
      if (navEl) navEl.classList.add('generated');
    }

    if (data.all_done || data.error) {
      es.close();
      ReportState.generating = false;
      if (btnAll) { btnAll.disabled = false; btnAll.innerHTML = '<span class=\'icon\' data-lucide=\'bot\'></span> Generate All'; }
      if (btnAllSec) { btnAllSec.disabled = false; btnAllSec.innerHTML = '<span class=\'icon\' data-lucide=\'bot\'></span> Generate All Sections'; }
      if (progressBlock) setTimeout(() => { progressBlock.style.display = 'none'; }, 3000);

      if (data.error) {
        showReportToast('Generation error: ' + data.error, 'error');
      } else {
        showReportToast(`${data.sections_generated} sections generated successfully! Run AI Review to score the report.`, 'success');
        // Re-render the report detail to show updated counts
        setTimeout(() => openReport(ReportState.currentReportId), 1000);
      }
    }
  };

  es.onerror = () => {
    es.close();
    ReportState.generating = false;
    if (btnAll) { btnAll.disabled = false; btnAll.innerHTML = '<span class=\'icon\' data-lucide=\'bot\'></span> Generate All'; }
    showReportToast('Stream connection error', 'error');
  };
};

/* ── AI Review ───────────────────────────────────────────────────────────────── */

window.runAIReview = async function () {
  if (!ReportState.currentReportId) return;
  const btn = document.getElementById('btn-ai-review');
  if (btn) { btn.disabled = true; btn.innerHTML = '<div class="report-spinner"></div> Reviewing...'; }

  const content = document.getElementById('review-content');
  if (content) content.innerHTML = '<div style="text-align:center;padding:60px;color:#66615B"><div class="report-spinner"></div><div style="margin-top:12px;font-size:13px">AI is reviewing the validation report for GMP compliance...</div></div>';

  switchReportTab('ai-review');

  try {
    const review = await rApi('/' + ReportState.currentReportId + '/review', { method: 'POST' });
    if (content) content.innerHTML = renderAIReview(review);
    // Update header scores
    if (ReportState.currentReport) {
      ReportState.currentReport.compliance_score = review.compliance_score;
      ReportState.currentReport.ai_readiness_score = review.readiness_score;
    }
    showReportToast('AI review completed', 'success');
  } catch (e) {
    if (content) content.innerHTML = `<div class="report-empty"><div class="report-empty-icon"><span class=\'icon\' data-lucide=\'alert-triangle\'></span></div><div class="report-empty-title">Review failed</div><div class="report-empty-sub">${e.message}</div></div>`;
    showReportToast('AI review error: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '<span class=\'icon\' data-lucide=\'search\'></span> AI Review'; }
  }
};

function renderAIReview(r) {
  const scoreColor = s => s >= 80 ? 'score-high' : s >= 60 ? 'score-medium' : 'score-low';
  const recClass = {
    'READY FOR QA APPROVAL': 'rec-ready',
    'MINOR REVISIONS REQUIRED': 'rec-minor',
    'MAJOR REVISIONS REQUIRED': 'rec-major',
    'NOT READY': 'rec-not-ready',
  }[r.recommendation] || 'rec-minor';

  const renderList = (items, cls = '') => items && items.length
    ? `<ul class="report-review-list">${items.map(i => {
        const text = typeof i === 'string' ? i : `<strong>${i.section}</strong> — ${i.comment} <span style="font-size:10px;color:#66615B">[${i.severity}]</span>`;
        const sev = typeof i === 'object' ? `severity-${(i.severity||'').toLowerCase()}` : '';
        return `<li class="${sev} ${cls}">${text}</li>`;
      }).join('')}</ul>`
    : '<div style="font-size:13px;color:#66615B;padding:8px">None identified</div>';

  return `
    <div class="report-review-scores">
      <div class="report-review-score-card">
        <div class="report-review-score-value ${scoreColor(r.compliance_score)}">${r.compliance_score}</div>
        <div class="report-review-score-label">Compliance Score</div>
      </div>
      <div class="report-review-score-card">
        <div class="report-review-score-value ${scoreColor(r.completeness_score)}">${r.completeness_score}</div>
        <div class="report-review-score-label">Completeness Score</div>
      </div>
      <div class="report-review-score-card">
        <div class="report-review-score-value ${scoreColor(r.readiness_score)}">${r.readiness_score}</div>
        <div class="report-review-score-label">Readiness Score</div>
      </div>
      <div class="report-review-score-card">
        <div class="report-review-score-value ${scoreColor(r.overall_score)}">${r.overall_score}</div>
        <div class="report-review-score-label">Overall Score</div>
      </div>
    </div>

    <div class="report-review-recommendation ${recClass}">
      <span style="font-size:18px">${r.recommendation === 'READY FOR QA APPROVAL' ? '<span class=\'icon\' data-lucide=\'check-circle-2\'></span>' : r.recommendation === 'MINOR REVISIONS REQUIRED' ? '<span class=\'icon\' data-lucide=\'alert-triangle\'></span>' : '<span class=\'icon\' data-lucide=\'circle-x\'></span>'}</span>
      ${r.recommendation}
    </div>

    ${r.executive_summary ? `<div class="report-panel" style="margin-bottom:20px">
      <div class="report-panel-header"><div class="report-panel-title">Executive Summary</div></div>
      <div class="report-panel-body" style="font-size:13px;color:#2D2A28;line-height:1.7">${r.executive_summary}</div>
    </div>` : ''}

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div>
        <div class="report-review-section">
          <div class="report-review-section-title"><span class=\'icon\' data-lucide=\'check-circle-2\'></span> Strengths</div>
          ${renderList(r.strengths, 'strength')}
        </div>
        <div class="report-review-section">
          <div class="report-review-section-title"><span class=\'icon\' data-lucide=\'clipboard-list\'></span> Missing Sections</div>
          ${renderList(r.missing_sections)}
        </div>
        <div class="report-review-section">
          <div class="report-review-section-title"><span class=\'icon\' data-lucide=\'search\'></span> Missing Evidence</div>
          ${renderList(r.missing_evidence)}
        </div>
      </div>
      <div>
        <div class="report-review-section">
          <div class="report-review-section-title"><span class=\'icon\' data-lucide=\'alert-triangle\'></span> Regulatory Gaps</div>
          ${renderList(r.regulatory_gaps)}
        </div>
        <div class="report-review-section">
          <div class="report-review-section-title"><span class=\'icon\' data-lucide=\'lock\'></span> Data Integrity Issues</div>
          ${renderList(r.data_integrity_issues)}
        </div>
        <div class="report-review-section">
          <div class="report-review-section-title"><span class=\'icon\' data-lucide=\'lightbulb\'></span> Improvements</div>
          ${renderList(r.improvements)}
        </div>
      </div>
    </div>

    ${r.reviewer_comments && r.reviewer_comments.length ? `
    <div class="report-review-section" style="margin-top:20px">
      <div class="report-review-section-title"><span class=\'icon\' data-lucide=\'message-square\'></span> Reviewer Comments</div>
      ${renderList(r.reviewer_comments)}
    </div>` : ''}`;
}

/* ── Traceability ────────────────────────────────────────────────────────────── */

window.loadTraceability = async function () {
  const content = document.getElementById('trace-content');
  if (!content || !ReportState.currentReportId) return;
  content.innerHTML = '<div style="text-align:center;padding:40px"><div class="report-spinner"></div><div style="margin-top:12px;font-size:13px;color:#66615B">Building traceability matrix...</div></div>';

  try {
    const matrix = await rApi('/' + ReportState.currentReportId + '/traceability');
    content.innerHTML = renderTraceabilityMatrix(matrix);
  } catch (e) {
    content.innerHTML = `<div class="report-empty"><div class="report-empty-icon"><span class=\'icon\' data-lucide=\'alert-triangle\'></span></div><div>${e.message}</div></div>`;
  }
};

function renderTraceabilityMatrix(m) {
  return `
    <div class="report-trace-summary">
      <div class="report-trace-card">
        <div class="report-trace-card-title">URS Requirements</div>
        <div class="report-trace-pct">${m.urs_coverage_pct}%</div>
        <div class="report-trace-detail">${m.covered_requirements} / ${m.total_requirements} covered</div>
      </div>
      <div class="report-trace-card">
        <div class="report-trace-card-title">Risk Items</div>
        <div class="report-trace-pct">${m.risk_coverage_pct}%</div>
        <div class="report-trace-detail">${m.covered_risks} / ${m.total_risks} covered</div>
      </div>
      <div class="report-trace-card">
        <div class="report-trace-card-title">Test Cases</div>
        <div class="report-trace-pct">${m.total_test_cases}</div>
        <div class="report-trace-detail">Total test cases across IQ/OQ/PQ</div>
      </div>
      <div class="report-trace-card">
        <div class="report-trace-card-title">Uncovered Requirements</div>
        <div class="report-trace-pct" style="color:${m.uncovered_requirements > 0 ? '#CE7975' : '#5F8A61'}">${m.uncovered_requirements}</div>
        <div class="report-trace-detail">${m.uncovered_requirements > 0 ? 'Need test coverage' : 'Full coverage achieved'}</div>
      </div>
    </div>

    ${m.requirements.length ? `
    <div class="report-panel" style="margin-bottom:20px">
      <div class="report-panel-header">
        <div class="report-panel-title">URS Requirements <span class=\'icon\' data-lucide=\'arrow-right\'></span> Test Cases</div>
        <div style="font-size:12px;color:#66615B">${m.covered_requirements}/${m.total_requirements} covered</div>
      </div>
      <div style="overflow-x:auto">
        <table class="report-trace-table">
          <thead><tr>
            <th>Req ID</th><th>Requirement</th><th>Priority</th><th>GMP</th><th>Test Cases</th><th>Status</th>
          </tr></thead>
          <tbody>
            ${m.requirements.map(r => `
            <tr>
              <td style="color:#2D2A28;font-weight:600">${r.req_id}</td>
              <td style="max-width:300px">${r.requirement}</td>
              <td>${r.priority}</td>
              <td>${r.gmp_criticality}</td>
              <td>
                <div class="trace-tc-list">
                  ${r.test_cases.length ? r.test_cases.map(tc => `<span class="trace-tc-chip">${tc}</span>`).join('') : '<span style="color:#66615B;font-size:11px">None</span>'}
                </div>
              </td>
              <td><span class="${r.covered ? 'trace-covered' : 'trace-uncovered'}">${r.covered ? '<span class=\'icon\' data-lucide=\'check\'></span> Covered' : '<span class=\'icon\' data-lucide=\'x\'></span> Gap'}</span></td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>` : ''}

    ${m.risks.length ? `
    <div class="report-panel">
      <div class="report-panel-header">
        <div class="report-panel-title">Risk Items <span class=\'icon\' data-lucide=\'arrow-right\'></span> Test Cases</div>
        <div style="font-size:12px;color:#66615B">${m.covered_risks}/${m.total_risks} covered</div>
      </div>
      <div style="overflow-x:auto">
        <table class="report-trace-table">
          <thead><tr>
            <th>Risk ID</th><th>Failure Mode</th><th>Risk Level</th><th>RPN</th><th>Test Cases</th><th>Status</th>
          </tr></thead>
          <tbody>
            ${m.risks.map(r => `
            <tr>
              <td style="color:#C59A41;font-weight:600">${r.item_id}</td>
              <td style="max-width:280px">${r.failure_mode}</td>
              <td>${r.risk_level}</td>
              <td>${r.rpn || '—'}</td>
              <td>
                <div class="trace-tc-list">
                  ${r.test_cases.length ? r.test_cases.map(tc => `<span class="trace-tc-chip">${tc}</span>`).join('') : '<span style="color:#66615B;font-size:11px">None</span>'}
                </div>
              </td>
              <td><span class="${r.covered ? 'trace-covered' : 'trace-uncovered'}">${r.covered ? '<span class=\'icon\' data-lucide=\'check\'></span> Covered' : '<span class=\'icon\' data-lucide=\'x\'></span> Gap'}</span></td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>` : ''}`;
}

/* ── Approval ────────────────────────────────────────────────────────────────── */

async function loadApprovalTrail() {
  const el = document.getElementById('approval-content');
  if (!el || !ReportState.currentReportId) return;
  try {
    const trail = await rApi('/' + ReportState.currentReportId + '/approval');
    el.innerHTML = renderApproval(trail);
  } catch (e) { el.innerHTML = `<div style="color:#CE7975">${e.message}</div>`; }
}

function renderApproval(trail) {
  const report = ReportState.currentReport;
  const statusFlow = ['draft','under_review','approved','released','archived'];

  return `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div>
        <div class="report-panel" style="margin-bottom:20px">
          <div class="report-panel-header"><div class="report-panel-title">Current Status</div></div>
          <div class="report-panel-body">
            <div style="display:flex;gap:0;flex-direction:column">
              ${statusFlow.map(s => {
                const active = report && report.status === s;
                const past = report && statusFlow.indexOf(report.status) > statusFlow.indexOf(s);
                return `<div style="display:flex;align-items:center;gap:12px;padding:8px 0;${!active && !past ? 'opacity:0.4' : ''}">
                  <div style="width:28px;height:28px;border-radius:50%;background:${active?'#9D7B60':past?'#3D6140':'#5B4C43'};display:flex;align-items:center;justify-content:center;font-size:14px">
                    ${active ? '●' : past ? '<span class=\'icon\' data-lucide=\'check\'></span>' : '○'}
                  </div>
                  <span style="font-size:13px;color:${active?'#8A6B52':past?'#5F8A61':'#66615B'};font-weight:${active?700:400};text-transform:capitalize">
                    ${s.replace('_',' ')}
                  </span>
                </div>`;
              }).join('')}
            </div>
          </div>
        </div>

        <!-- Submit action -->
        <div class="report-panel">
          <div class="report-panel-header"><div class="report-panel-title">Submit Action</div></div>
          <div class="report-panel-body">
            <div class="report-form-grid" style="grid-template-columns:1fr">
              <div class="report-field">
                <label>Action</label>
                <select id="appr-action">
                  <option>Submit for Review</option>
                  <option>Technical Review Approved</option>
                  <option>QA Approved</option>
                  <option>Released</option>
                  <option>Archived</option>
                  <option>Rejected</option>
                  <option>Obsolete</option>
                </select>
              </div>
              <div class="report-field">
                <label>Performed By</label>
                <input type="text" id="appr-by" placeholder="Your name">
              </div>
              <div class="report-field">
                <label>Role</label>
                <input type="text" id="appr-role" placeholder="QA Manager, Author...">
              </div>
              <div class="report-field">
                <label>Comments</label>
                <textarea id="appr-comments" rows="3" placeholder="Approval comments..."></textarea>
              </div>
              <div class="report-field">
                <label>Electronic Signature</label>
                <input type="text" id="appr-sig" placeholder="Digital signature / initials">
              </div>
              <button class="report-btn report-btn-success" onclick="submitApprovalAction()">Submit</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Timeline -->
      <div class="report-panel">
        <div class="report-panel-header"><div class="report-panel-title">Approval History</div></div>
        <div class="report-panel-body">
          ${trail.length === 0
            ? '<div class="report-empty" style="padding:20px">No approval actions yet</div>'
            : `<div class="report-approval-timeline">
                ${[...trail].reverse().map(a => `
                <div class="report-approval-entry">
                  <div class="report-approval-action">${a.action}</div>
                  <div class="report-approval-meta">${a.performed_by} ${a.role ? '· ' + a.role : ''} · ${(a.created_at||'').slice(0,16)}</div>
                  ${a.comments ? `<div class="report-approval-comment">${a.comments}</div>` : ''}
                </div>`).join('')}
              </div>`}
        </div>
      </div>
    </div>`;
}

async function submitApprovalAction() {
  const payload = {
    action: v('appr-action'),
    performed_by: v('appr-by'),
    role: v('appr-role'),
    comments: v('appr-comments'),
    electronic_sig: v('appr-sig'),
  };
  if (!payload.performed_by) { showReportToast('Please enter your name', 'error'); return; }

  try {
    await rApi('/' + ReportState.currentReportId + '/approval', { method: 'POST', body: JSON.stringify(payload) });
    const report = await rApi('/' + ReportState.currentReportId);
    ReportState.currentReport = report;
    showReportToast('Action submitted successfully', 'success');
    loadApprovalTrail();
  } catch (e) {
    showReportToast('Error: ' + e.message, 'error');
  }
}

window.submitForApproval = function () {
  switchReportTab('approval');
  const actionSel = document.getElementById('appr-action');
  if (actionSel) actionSel.value = 'Submit for Review';
};

/* ── Versions ────────────────────────────────────────────────────────────────── */

async function loadVersionHistory() {
  const el = document.getElementById('versions-content');
  if (!el || !ReportState.currentReportId) return;
  try {
    const versions = await rApi('/' + ReportState.currentReportId + '/versions');
    el.innerHTML = renderVersionHistory(versions);
  } catch (e) { el.innerHTML = `<div style="color:#CE7975">${e.message}</div>`; }
}

function renderVersionHistory(versions) {
  return `
    <div style="display:flex;justify-content:flex-end;margin-bottom:16px">
      <button class="report-btn report-btn-outline report-btn-sm" onclick="createVersionSnapshot()"><span class=\'icon\' data-lucide=\'camera\'></span> Create Snapshot</button>
    </div>
    ${versions.length === 0
      ? '<div class="report-empty" style="padding:30px"><div class="report-empty-icon"><span class=\'icon\' data-lucide=\'book-open\'></span></div><div class="report-empty-title">No version snapshots yet</div></div>'
      : `<table class="report-list-table">
          <thead><tr><th>Version</th><th>Revision</th><th>Status</th><th>Compliance</th><th>Completeness</th><th>Created By</th><th>Date</th></tr></thead>
          <tbody>
            ${versions.map(v => `
            <tr>
              <td><strong style="color:#2D2A28">${v.version}</strong></td>
              <td>${v.revision}</td>
              <td><span class="report-badge badge-${v.status}">${v.status}</span></td>
              <td>${v.compliance_score}%</td>
              <td>${v.completeness_score}%</td>
              <td>${v.created_by}</td>
              <td style="font-size:11px;color:#66615B">${(v.created_at||'').slice(0,16)}</td>
            </tr>`).join('')}
          </tbody>
        </table>`
    }`;
}

async function createVersionSnapshot() {
  const summary = prompt('Enter change summary for this version snapshot:');
  if (summary === null) return;
  const by = prompt('Your name:') || 'QA';
  try {
    await rApi('/' + ReportState.currentReportId + '/versions', {
      method: 'POST',
      body: JSON.stringify({ change_summary: summary, created_by: by }),
    });
    showReportToast('Version snapshot created', 'success');
    loadVersionHistory();
  } catch (e) {
    showReportToast('Error: ' + e.message, 'error');
  }
}

/* ── Tabs ────────────────────────────────────────────────────────────────────── */

window.switchReportTab = function (tab) {
  ReportState.currentTab = tab;
  document.querySelectorAll('.report-tab').forEach(t => t.classList.toggle('active', t.textContent.toLowerCase().replace(/\s+/g, '-').includes(tab) || t.getAttribute('onclick') && t.getAttribute('onclick').includes(`'${tab}'`)));
  document.querySelectorAll('.report-tab-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById('rtab-' + tab);
  if (panel) panel.classList.add('active');
  // Lazy load
  if (tab === 'traceability' && !document.getElementById('trace-content').children.length) loadTraceability();
};

/* ── Export ──────────────────────────────────────────────────────────────────── */

window.exportReportDocx = function (id) {
  window.location.href = `/report/${id}/export/docx`;
  showReportToast('Downloading DOCX...', 'success');
};

/* ── Helpers ─────────────────────────────────────────────────────────────────── */

function v(id) {
  const el = document.getElementById(id);
  return el ? el.value : '';
}

function esc(str) {
  return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function showReportToast(msg, type = '') {
  const existing = document.querySelector('.report-toast');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.className = 'report-toast ' + type;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

/* ── Sidebar collapse ────────────────────────────────────────────────────────── */

window.toggleReportSection = function () {
  const items = document.getElementById('report-nav-items');
  const btn   = document.getElementById('report-collapse-btn');
  if (!items) return;
  const hidden = items.style.display === 'none';
  items.style.display = hidden ? 'block' : 'none';
  if (btn) btn.textContent = hidden ? '▲' : '▼';
};
