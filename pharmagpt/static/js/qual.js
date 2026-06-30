/**
 * qual.js — Qualification Management Suite frontend
 * IQ / OQ / PQ protocol management, execution, AI review, and traceability.
 */

/* ── State ──────────────────────────────────────────────────────────────────── */
const QualState = {
  activeQualId: null,
  activeProtocolId: null,
  activeProtocolType: null,
  activeTab: 'dashboard',
  qualList: [],
  protocols: {},
  testCases: {},
  executions: {},
  generating: false,
};

/* ── Init ────────────────────────────────────────────────────────────────────── */
function initQual() {
  showView('view-qual');
  qualShowDashboard();
}

/* ── Navigation helpers ──────────────────────────────────────────────────────── */
function qualShowTab(tabId) {
  document.querySelectorAll('#qual-tab-bar .qual-tab').forEach(t => t.classList.remove('active'));
  const tab = document.getElementById('qual-tab-' + tabId);
  if (tab) tab.classList.add('active');
  document.querySelectorAll('.qual-tab-pane').forEach(p => p.style.display = 'none');
  const pane = document.getElementById('qual-pane-' + tabId);
  if (pane) pane.style.display = 'block';
  QualState.activeTab = tabId;
}

function qualShowDashboard() {
  qualShowTab('dashboard');
  loadQualDashboard();
}

function qualShowList() {
  qualShowTab('list');
  loadQualList();
}

function qualShowNew() {
  qualShowTab('new');
  renderQualForm(null);
}

function qualShowDetail(qualId) {
  QualState.activeQualId = qualId;
  qualShowTab('detail');
  loadQualDetail(qualId);
}

/* ── Dashboard ───────────────────────────────────────────────────────────────── */
async function loadQualDashboard() {
  const pane = document.getElementById('qual-pane-dashboard');
  pane.innerHTML = '<div class="qual-loading">Loading dashboard…</div>';
  try {
    const res = await fetch('/qual/dashboard');
    const d = await res.json();
    pane.innerHTML = renderQualDashboard(d);
  } catch (e) {
    pane.innerHTML = `<div class="qual-empty"><div class="qual-empty-icon">⚠️</div><div class="qual-empty-text">Failed to load dashboard</div></div>`;
  }
}

function renderQualDashboard(d) {
  const pct = d.total > 0 ? Math.round((d.completed + d.approved) / d.total * 100) : 0;
  return `
    <div class="qual-dash-stats">
      <div class="qual-stat-card"><div class="qual-stat-icon">📋</div><div class="qual-stat-value">${d.total}</div><div class="qual-stat-label">Total Qualifications</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">✅</div><div class="qual-stat-value">${d.iq_complete}</div><div class="qual-stat-label">IQ Complete</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">✅</div><div class="qual-stat-value">${d.oq_complete}</div><div class="qual-stat-label">OQ Complete</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">✅</div><div class="qual-stat-value">${d.pq_complete}</div><div class="qual-stat-label">PQ Complete</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">🧪</div><div class="qual-stat-value">${d.total_tests}</div><div class="qual-stat-label">Total Tests</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">✔️</div><div class="qual-stat-value">${d.pass_count}</div><div class="qual-stat-label">Tests Passed</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">❌</div><div class="qual-stat-value">${d.fail_count}</div><div class="qual-stat-label">Tests Failed</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">⚠️</div><div class="qual-stat-value">${d.open_deviations}</div><div class="qual-stat-label">Open Deviations</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">⏳</div><div class="qual-stat-value">${d.pending_approvals}</div><div class="qual-stat-label">Pending Approvals</div></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:20px;">
      <div class="qual-card">
        <div class="qual-card-header"><span class="qual-card-title">Overall Qualification Progress</span></div>
        <div class="qual-progress-row">
          <span class="qual-progress-label">Completed</span>
          <div class="qual-progress-bar-track"><div class="qual-progress-bar-fill" style="width:${pct}%"></div></div>
          <span class="qual-progress-pct">${pct}%</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:14px;text-align:center;font-size:12px;">
          <div><div style="font-size:20px;font-weight:800;color:#1565C0">${d.draft}</div><div style="color:#888">Draft</div></div>
          <div><div style="font-size:20px;font-weight:800;color:#F57F17">${d.in_progress}</div><div style="color:#888">In Progress</div></div>
          <div><div style="font-size:20px;font-weight:800;color:#1B5E20">${d.approved}</div><div style="color:#888">Approved</div></div>
        </div>
      </div>
      <div class="qual-card">
        <div class="qual-card-header"><span class="qual-card-title">Test Execution Status</span></div>
        ${d.total_tests > 0 ? `
        <div class="qual-progress-row">
          <span class="qual-progress-label">Pass</span>
          <div class="qual-progress-bar-track"><div class="qual-progress-bar-fill" style="width:${Math.round(d.pass_count/d.total_tests*100)}%;background:linear-gradient(90deg,#43A047,#1B5E20)"></div></div>
          <span class="qual-progress-pct">${d.pass_count}</span>
        </div>
        <div class="qual-progress-row">
          <span class="qual-progress-label">Fail</span>
          <div class="qual-progress-bar-track"><div class="qual-progress-bar-fill" style="width:${Math.round(d.fail_count/d.total_tests*100)}%;background:linear-gradient(90deg,#EF5350,#B71C1C)"></div></div>
          <span class="qual-progress-pct">${d.fail_count}</span>
        </div>` : '<div class="qual-empty" style="padding:20px"><div class="qual-empty-icon" style="font-size:28px">🧪</div><div class="qual-empty-text" style="font-size:12px">No tests executed yet</div></div>'}
      </div>
    </div>

    <div class="qual-card">
      <div class="qual-card-header">
        <span class="qual-card-title">Recent Qualifications</span>
        <button class="btn-qual-outline" onclick="qualShowList()">View All</button>
      </div>
      ${d.recent && d.recent.length ? `
      <div class="qual-table-wrapper">
        <table class="qual-table">
          <thead><tr><th>Qual #</th><th>Equipment</th><th>Status</th><th>IQ</th><th>OQ</th><th>PQ</th><th>Created</th><th></th></tr></thead>
          <tbody>
            ${d.recent.map(q => `
              <tr>
                <td>${q.qual_number || '—'}</td>
                <td><strong>${q.equipment_name || q.title}</strong></td>
                <td>${qualStatusBadge(q.status)}</td>
                <td>${qualPhasePill('IQ', q.iq_status)}</td>
                <td>${qualPhasePill('OQ', q.oq_status)}</td>
                <td>${qualPhasePill('PQ', q.pq_status)}</td>
                <td style="font-size:11px;color:#888">${q.created_at ? q.created_at.split('T')[0] : ''}</td>
                <td><button class="btn-qual-outline" onclick="qualShowDetail(${q.id})" style="padding:4px 10px;font-size:11px">Open</button></td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>` : '<div class="qual-empty" style="padding:20px"><div class="qual-empty-icon" style="font-size:28px">📋</div><div class="qual-empty-text">No qualifications yet</div><button class="btn-qual-primary" onclick="qualShowNew()">+ New Qualification</button></div>'}
    </div>`;
}

/* ── List ────────────────────────────────────────────────────────────────────── */
async function loadQualList() {
  const pane = document.getElementById('qual-pane-list');
  pane.innerHTML = `
    <div class="qual-filters">
      <input class="qual-filter-input" id="qual-search" placeholder="Search qualifications…" oninput="filterQualList()" />
      <select class="qual-filter-select" id="qual-filter-status" onchange="filterQualList()">
        <option value="">All Status</option>
        <option value="draft">Draft</option>
        <option value="in_progress">In Progress</option>
        <option value="completed">Completed</option>
        <option value="approved">Approved</option>
        <option value="under_review">Under Review</option>
      </select>
      <select class="qual-filter-select" id="qual-filter-category" onchange="filterQualList()">
        <option value="">All Categories</option>
        <option value="Manufacturing Equipment">Manufacturing Equipment</option>
        <option value="Packaging Equipment">Packaging Equipment</option>
        <option value="Laboratory Equipment">Laboratory Equipment</option>
        <option value="Utilities">Utilities</option>
        <option value="HVAC">HVAC</option>
        <option value="Computerized System">Computerized System</option>
      </select>
      <button class="btn-qual-primary" onclick="qualShowNew()">+ New Qualification</button>
    </div>
    <div id="qual-list-body"><div class="qual-loading">Loading…</div></div>`;
  await refreshQualListBody();
}

async function refreshQualListBody() {
  try {
    const res = await fetch('/qual/');
    QualState.qualList = await res.json();
    renderQualListBody(QualState.qualList);
  } catch (e) {
    document.getElementById('qual-list-body').innerHTML = '<div class="qual-empty">Failed to load</div>';
  }
}

function filterQualList() {
  const q = (document.getElementById('qual-search')?.value || '').toLowerCase();
  const status = document.getElementById('qual-filter-status')?.value || '';
  const category = document.getElementById('qual-filter-category')?.value || '';
  const filtered = QualState.qualList.filter(qual => {
    const matchQ = !q || (qual.equipment_name || '').toLowerCase().includes(q) || (qual.title || '').toLowerCase().includes(q) || (qual.qual_number || '').toLowerCase().includes(q);
    const matchS = !status || qual.status === status;
    const matchC = !category || qual.category === category;
    return matchQ && matchS && matchC;
  });
  renderQualListBody(filtered);
}

function renderQualListBody(list) {
  const body = document.getElementById('qual-list-body');
  if (!list || !list.length) {
    body.innerHTML = `<div class="qual-empty"><div class="qual-empty-icon">📋</div><div class="qual-empty-text">No qualifications found</div><button class="btn-qual-primary" onclick="qualShowNew()">+ New Qualification</button></div>`;
    return;
  }
  body.innerHTML = `
    <div class="qual-table-wrapper">
      <table class="qual-table">
        <thead><tr><th>Qual #</th><th>Equipment</th><th>Category</th><th>Department</th><th>Status</th><th>IQ</th><th>OQ</th><th>PQ</th><th>Date</th><th></th></tr></thead>
        <tbody>
          ${list.map(q => `
            <tr>
              <td><strong>${q.qual_number || '—'}</strong></td>
              <td>
                <div style="font-weight:600;font-size:13px">${q.equipment_name || q.title}</div>
                ${q.manufacturer ? `<div style="font-size:11px;color:#888">${q.manufacturer} ${q.model || ''}</div>` : ''}
              </td>
              <td style="font-size:12px">${q.category || '—'}</td>
              <td style="font-size:12px">${q.department || '—'}</td>
              <td>${qualStatusBadge(q.status)}</td>
              <td>${qualPhasePill('IQ', q.iq_status)}</td>
              <td>${qualPhasePill('OQ', q.oq_status)}</td>
              <td>${qualPhasePill('PQ', q.pq_status)}</td>
              <td style="font-size:11px;color:#888">${q.created_at ? q.created_at.split('T')[0] : ''}</td>
              <td>
                <button class="btn-qual-outline" onclick="qualShowDetail(${q.id})" style="padding:4px 10px;font-size:11px">Open</button>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

/* ── Create / Edit Form ──────────────────────────────────────────────────────── */
function renderQualForm(qual) {
  const pane = document.getElementById('qual-pane-new');
  const isEdit = !!qual;
  pane.innerHTML = `
    <div class="qual-wizard">
      <div class="qual-form-section">
        <div class="qual-form-section-title">🏷️ Qualification Identification</div>
        <div class="qual-form-grid">
          <div class="qual-form-group">
            <label>Qualification Number</label>
            <input type="text" id="qf-qual-number" value="${qual?.qual_number || ''}" placeholder="e.g. QUAL-2024-001" />
          </div>
          <div class="qual-form-group">
            <label>Revision</label>
            <input type="text" id="qf-revision" value="${qual?.revision || 'A'}" />
          </div>
          <div class="qual-form-group">
            <label>Validation Type</label>
            <select id="qf-validation-type">
              ${['IQ/OQ/PQ','IQ Only','OQ Only','PQ Only','IQ/OQ','OQ/PQ','CSV','Re-qualification'].map(v =>
                `<option${(qual?.validation_type||'IQ/OQ/PQ')===v?' selected':''}>${v}</option>`).join('')}
            </select>
          </div>
          <div class="qual-form-group">
            <label>Category</label>
            <select id="qf-category">
              ${['','Manufacturing Equipment','Packaging Equipment','Laboratory Equipment','Utilities','HVAC','Computerized System','SCADA','BMS','MES','LIMS','ERP','Barcode System','Serialization','Vision System'].map(v =>
                `<option value="${v}"${(qual?.category||'')=== v?' selected':''}>${v||'Select category…'}</option>`).join('')}
            </select>
          </div>
        </div>
      </div>

      <div class="qual-form-section">
        <div class="qual-form-section-title">🔧 Equipment Information</div>
        <div class="qual-form-grid">
          <div class="qual-form-group">
            <label>Equipment Name <span class="required">*</span></label>
            <input type="text" id="qf-equipment-name" value="${qual?.equipment_name || ''}" placeholder="e.g. Tablet Compression Machine" />
          </div>
          <div class="qual-form-group">
            <label>Equipment ID / Tag</label>
            <input type="text" id="qf-equipment-id" value="${qual?.equipment_id || ''}" placeholder="e.g. EQ-TCM-001" />
          </div>
          <div class="qual-form-group">
            <label>Manufacturer</label>
            <input type="text" id="qf-manufacturer" value="${qual?.manufacturer || ''}" placeholder="e.g. Fette Compacting" />
          </div>
          <div class="qual-form-group">
            <label>Model</label>
            <input type="text" id="qf-model" value="${qual?.model || ''}" placeholder="e.g. FE35" />
          </div>
          <div class="qual-form-group">
            <label>Serial Number</label>
            <input type="text" id="qf-serial" value="${qual?.serial_number || ''}" placeholder="e.g. SN-2024-0012" />
          </div>
          <div class="qual-form-group">
            <label>Capacity</label>
            <input type="text" id="qf-capacity" value="${qual?.capacity || ''}" placeholder="e.g. 150,000 tablets/hr" />
          </div>
          <div class="qual-form-group">
            <label>Equipment Type</label>
            <input type="text" id="qf-equipment-type" value="${qual?.equipment_type || ''}" placeholder="e.g. Rotary Tablet Press" />
          </div>
          <div class="qual-form-group">
            <label>Department</label>
            <input type="text" id="qf-department" value="${qual?.department || ''}" placeholder="e.g. Manufacturing" />
          </div>
          <div class="qual-form-group">
            <label>Site</label>
            <input type="text" id="qf-site" value="${qual?.site || ''}" />
          </div>
          <div class="qual-form-group">
            <label>Location</label>
            <input type="text" id="qf-location" value="${qual?.location || ''}" placeholder="e.g. Room 102, Block A" />
          </div>
        </div>
      </div>

      <div class="qual-form-section">
        <div class="qual-form-section-title">🔗 Module Integration</div>
        <div class="qual-form-grid">
          <div class="qual-form-group">
            <label>Linked URS ID</label>
            <input type="number" id="qf-urs-id" value="${qual?.linked_urs_id || ''}" placeholder="URS record ID (auto-links traceability)" />
          </div>
          <div class="qual-form-group">
            <label>Linked Risk Assessment ID</label>
            <input type="number" id="qf-risk-id" value="${qual?.linked_risk_id || ''}" placeholder="Risk assessment ID (auto-links traceability)" />
          </div>
          <div class="qual-form-group">
            <label>Linked Project ID</label>
            <input type="number" id="qf-project-id" value="${qual?.linked_project_id || ''}" placeholder="Project ID" />
          </div>
        </div>
      </div>

      <div class="qual-form-section">
        <div class="qual-form-section-title">📝 Description</div>
        <div class="qual-form-grid">
          <div class="qual-form-group full-width">
            <label>Purpose</label>
            <textarea id="qf-purpose" rows="2" placeholder="Purpose of this qualification…">${qual?.purpose || ''}</textarea>
          </div>
          <div class="qual-form-group full-width">
            <label>Scope</label>
            <textarea id="qf-scope" rows="2" placeholder="Scope of qualification activities…">${qual?.scope || ''}</textarea>
          </div>
          <div class="qual-form-group full-width">
            <label>System Description</label>
            <textarea id="qf-system-desc" rows="3" placeholder="Describe the system/equipment…">${qual?.system_description || ''}</textarea>
          </div>
          <div class="qual-form-group full-width">
            <label>Process Description</label>
            <textarea id="qf-process-desc" rows="2" placeholder="Manufacturing process description…">${qual?.process_description || ''}</textarea>
          </div>
        </div>
      </div>

      <div class="qual-form-section">
        <div class="qual-form-section-title">👥 Personnel & Dates</div>
        <div class="qual-form-grid three-col">
          <div class="qual-form-group">
            <label>Prepared By</label>
            <input type="text" id="qf-prepared-by" value="${qual?.prepared_by || ''}" />
          </div>
          <div class="qual-form-group">
            <label>Reviewed By</label>
            <input type="text" id="qf-reviewed-by" value="${qual?.reviewed_by || ''}" />
          </div>
          <div class="qual-form-group">
            <label>Approved By</label>
            <input type="text" id="qf-approved-by" value="${qual?.approved_by || ''}" />
          </div>
          <div class="qual-form-group">
            <label>Effective Date</label>
            <input type="date" id="qf-effective-date" value="${qual?.effective_date || ''}" />
          </div>
          <div class="qual-form-group">
            <label>Planned Start</label>
            <input type="date" id="qf-planned-start" value="${qual?.planned_start || ''}" />
          </div>
          <div class="qual-form-group">
            <label>Planned End</label>
            <input type="date" id="qf-planned-end" value="${qual?.planned_end || ''}" />
          </div>
        </div>
      </div>

      <div style="display:flex;gap:12px;justify-content:flex-end">
        <button class="btn-qual-outline" onclick="qualShowList()">Cancel</button>
        <button class="btn-qual-primary" onclick="saveQualification(${isEdit ? qual.id : 'null'})">
          ${isEdit ? '💾 Save Changes' : '✅ Create Qualification'}
        </button>
      </div>
    </div>`;
}

async function saveQualification(qualId) {
  const name = document.getElementById('qf-equipment-name')?.value?.trim();
  if (!name) { alert('Equipment name is required'); return; }

  const payload = {
    qual_number:        document.getElementById('qf-qual-number')?.value?.trim(),
    revision:           document.getElementById('qf-revision')?.value?.trim() || 'A',
    validation_type:    document.getElementById('qf-validation-type')?.value,
    category:           document.getElementById('qf-category')?.value,
    equipment_name:     name,
    equipment_id:       document.getElementById('qf-equipment-id')?.value?.trim(),
    manufacturer:       document.getElementById('qf-manufacturer')?.value?.trim(),
    model:              document.getElementById('qf-model')?.value?.trim(),
    serial_number:      document.getElementById('qf-serial')?.value?.trim(),
    capacity:           document.getElementById('qf-capacity')?.value?.trim(),
    equipment_type:     document.getElementById('qf-equipment-type')?.value?.trim(),
    department:         document.getElementById('qf-department')?.value?.trim(),
    site:               document.getElementById('qf-site')?.value?.trim(),
    location:           document.getElementById('qf-location')?.value?.trim(),
    linked_urs_id:      parseInt(document.getElementById('qf-urs-id')?.value) || null,
    linked_risk_id:     parseInt(document.getElementById('qf-risk-id')?.value) || null,
    linked_project_id:  parseInt(document.getElementById('qf-project-id')?.value) || null,
    purpose:            document.getElementById('qf-purpose')?.value?.trim(),
    scope:              document.getElementById('qf-scope')?.value?.trim(),
    system_description: document.getElementById('qf-system-desc')?.value?.trim(),
    process_description:document.getElementById('qf-process-desc')?.value?.trim(),
    prepared_by:        document.getElementById('qf-prepared-by')?.value?.trim(),
    reviewed_by:        document.getElementById('qf-reviewed-by')?.value?.trim(),
    approved_by:        document.getElementById('qf-approved-by')?.value?.trim(),
    effective_date:     document.getElementById('qf-effective-date')?.value,
    planned_start:      document.getElementById('qf-planned-start')?.value,
    planned_end:        document.getElementById('qf-planned-end')?.value,
  };

  try {
    const url = qualId ? `/qual/${qualId}` : '/qual/';
    const method = qualId ? 'PUT' : 'POST';
    const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!res.ok) throw new Error(await res.text());
    const qual = await res.json();
    qualShowDetail(qual.id);
  } catch (e) {
    alert('Save failed: ' + e.message);
  }
}

/* ── Detail View ─────────────────────────────────────────────────────────────── */
async function loadQualDetail(qualId) {
  const pane = document.getElementById('qual-pane-detail');
  pane.innerHTML = '<div class="qual-loading">Loading…</div>';
  try {
    const [qualRes, protRes] = await Promise.all([
      fetch(`/qual/${qualId}`),
      fetch(`/qual/${qualId}/protocols`),
    ]);
    const qual = await qualRes.json();
    const protocols = await protRes.json();
    QualState.protocols[qualId] = protocols;
    pane.innerHTML = renderQualDetail(qual, protocols);
  } catch (e) {
    pane.innerHTML = '<div class="qual-empty">Failed to load qualification</div>';
  }
}

function renderQualDetail(qual, protocols) {
  const iqProt = protocols.find(p => p.protocol_type === 'IQ');
  const oqProt = protocols.find(p => p.protocol_type === 'OQ');
  const pqProt = protocols.find(p => p.protocol_type === 'PQ');

  return `
    <!-- Header -->
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap;">
      <div style="flex:1;min-width:200px">
        <div style="font-size:20px;font-weight:800;color:var(--navy)">${qual.equipment_name || qual.title}</div>
        <div style="font-size:13px;color:#666;margin-top:2px">${qual.qual_number || 'No number assigned'} · Rev ${qual.revision} · ${qual.department || 'No department'}</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        ${qualStatusBadge(qual.status)}
        <button class="btn-qual-secondary" onclick="renderQualForm(${JSON.stringify(qual).replace(/"/g,'&quot;')});qualShowTab('new')" style="padding:7px 14px;font-size:12px">✏️ Edit</button>
        <button class="btn-qual-danger" onclick="deleteQualification(${qual.id})" style="font-size:12px">🗑️ Delete</button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="qual-tabs" id="qual-detail-tabs">
      <button class="qual-tab active" onclick="qualDetailTab('overview',${qual.id})">📋 Overview</button>
      <button class="qual-tab" onclick="qualDetailTab('protocols',${qual.id})">🧪 Protocols</button>
      <button class="qual-tab" onclick="qualDetailTab('execution',${qual.id})">▶️ Execution</button>
      <button class="qual-tab" onclick="qualDetailTab('deviations',${qual.id})">⚠️ Deviations</button>
      <button class="qual-tab" onclick="qualDetailTab('traceability',${qual.id})">🔗 Traceability</button>
      <button class="qual-tab" onclick="qualDetailTab('approvals',${qual.id})">✅ Approvals</button>
      <button class="qual-tab" onclick="qualDetailTab('versions',${qual.id})">📜 History</button>
    </div>

    <div id="qual-detail-content">
      ${renderQualOverview(qual, iqProt, oqProt, pqProt)}
    </div>`;
}

function qualDetailTab(tab, qualId) {
  document.querySelectorAll('#qual-detail-tabs .qual-tab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  const content = document.getElementById('qual-detail-content');
  switch (tab) {
    case 'overview':    loadQualDetailPane(qualId); break;
    case 'protocols':   loadProtocolsPane(qualId); break;
    case 'execution':   loadExecutionPane(qualId); break;
    case 'deviations':  loadDeviationsPane(qualId); break;
    case 'traceability':loadTraceabilityPane(qualId); break;
    case 'approvals':   loadApprovalsPane(qualId); break;
    case 'versions':    loadVersionsPane(qualId); break;
  }
}

async function loadQualDetailPane(qualId) {
  const [qualRes, protRes] = await Promise.all([fetch(`/qual/${qualId}`), fetch(`/qual/${qualId}/protocols`)]);
  const qual = await qualRes.json();
  const protocols = await protRes.json();
  const iqProt = protocols.find(p => p.protocol_type === 'IQ');
  const oqProt = protocols.find(p => p.protocol_type === 'OQ');
  const pqProt = protocols.find(p => p.protocol_type === 'PQ');
  document.getElementById('qual-detail-content').innerHTML = renderQualOverview(qual, iqProt, oqProt, pqProt);
}

function renderQualOverview(qual, iqProt, oqProt, pqProt) {
  return `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
      <div class="qual-card">
        <div class="qual-card-header"><span class="qual-card-title">Equipment Details</span></div>
        <table style="width:100%;font-size:12px;border-collapse:collapse">
          ${[
            ['Equipment Name', qual.equipment_name],
            ['Equipment ID', qual.equipment_id],
            ['Manufacturer', qual.manufacturer],
            ['Model', qual.model],
            ['Serial Number', qual.serial_number],
            ['Capacity', qual.capacity],
            ['Category', qual.category],
            ['Department', qual.department],
            ['Location', qual.location],
            ['Validation Type', qual.validation_type],
          ].map(([k,v]) => `<tr><td style="padding:5px 0;color:#888;font-weight:600;width:40%">${k}</td><td style="padding:5px 0;color:#333">${v||'—'}</td></tr>`).join('')}
        </table>
      </div>
      <div class="qual-card">
        <div class="qual-card-header"><span class="qual-card-title">Qualification Status</span></div>
        <div style="display:flex;flex-direction:column;gap:10px">
          ${[
            ['IQ Protocol', qual.iq_status, iqProt],
            ['OQ Protocol', qual.oq_status, oqProt],
            ['PQ Protocol', qual.pq_status, pqProt],
          ].map(([label, status, prot]) => `
            <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:#f8fbff;border-radius:8px;border:1px solid #E3F2FD">
              <div>
                <div style="font-size:13px;font-weight:700;color:var(--navy)">${label}</div>
                ${prot ? `<div style="font-size:11px;color:#888">${prot.pass_count || 0} pass / ${prot.fail_count || 0} fail</div>` : '<div style="font-size:11px;color:#aaa">Not created</div>'}
              </div>
              <div style="display:flex;align-items:center;gap:8px">
                ${qualPhasePill(label.split(' ')[0], status)}
                ${prot ? `<button class="btn-qual-outline" onclick="openProtocol(${qual.id},${prot.id},'${prot.protocol_type}')" style="padding:4px 10px;font-size:11px">Open</button>` :
                  `<button class="btn-qual-primary" onclick="createProtocol(${qual.id},'${label.split(' ')[0]}')" style="padding:4px 10px;font-size:11px">Create</button>`}
              </div>
            </div>`).join('')}
        </div>
      </div>
    </div>
    ${qual.purpose || qual.scope ? `
    <div class="qual-card" style="margin-top:18px">
      <div class="qual-card-header"><span class="qual-card-title">Scope & Purpose</span></div>
      ${qual.purpose ? `<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:700;color:#888;margin-bottom:4px">PURPOSE</div><div style="font-size:13px;color:#333">${qual.purpose}</div></div>` : ''}
      ${qual.scope ? `<div><div style="font-size:11px;font-weight:700;color:#888;margin-bottom:4px">SCOPE</div><div style="font-size:13px;color:#333">${qual.scope}</div></div>` : ''}
    </div>` : ''}`;
}

/* ── Protocols Tab ───────────────────────────────────────────────────────────── */
async function loadProtocolsPane(qualId) {
  const content = document.getElementById('qual-detail-content');
  content.innerHTML = '<div class="qual-loading">Loading protocols…</div>';
  try {
    const res = await fetch(`/qual/${qualId}/protocols`);
    const protocols = await res.json();
    content.innerHTML = renderProtocolsPane(qualId, protocols);
  } catch (e) {
    content.innerHTML = '<div class="qual-empty">Failed to load</div>';
  }
}

function renderProtocolsPane(qualId, protocols) {
  const types = ['IQ', 'OQ', 'PQ'];
  const protMap = {};
  protocols.forEach(p => protMap[p.protocol_type] = p);

  return `
    <div class="qual-protocol-cards">
      ${types.map(ptype => {
        const prot = protMap[ptype];
        const total = (prot?.pass_count || 0) + (prot?.fail_count || 0) + (prot?.pending_count || 0);
        const pct = total > 0 ? Math.round((prot.pass_count || 0) / total * 100) : 0;
        return `
        <div class="qual-protocol-card ${ptype.toLowerCase()}" onclick="${prot ? `openProtocol(${qualId},${prot.id},'${ptype}')` : `createProtocol(${qualId},'${ptype}')`}">
          <div class="qual-protocol-card-type">${ptype}</div>
          <div class="qual-protocol-card-title">${prot ? prot.title : `${ptype} Protocol`}</div>
          ${prot ? `
          <div class="qual-protocol-card-meta">
            <span>${qualStatusBadge(prot.status)}</span>
            <span>Rev ${prot.revision}</span>
            <span>${total} tests</span>
          </div>
          <div class="qual-progress-row" style="margin:0">
            <div class="qual-progress-bar-track" style="flex:1"><div class="qual-progress-bar-fill" style="width:${pct}%"></div></div>
            <span class="qual-progress-pct">${pct}%</span>
          </div>
          <div class="qual-protocol-card-actions" onclick="event.stopPropagation()">
            <button class="btn-qual-outline" onclick="openProtocol(${qualId},${prot.id},'${ptype}')">Open Protocol</button>
            <button class="btn-qual-primary" onclick="exportProtocol(${qualId},${prot.id})">⬇ DOCX</button>
          </div>` : `
          <div class="qual-empty" style="padding:16px 0;text-align:left">
            <div style="font-size:12px;color:#aaa;margin-bottom:8px">Protocol not created yet</div>
            <button class="btn-qual-primary" style="font-size:12px" onclick="event.stopPropagation();createProtocol(${qualId},'${ptype}')">+ Create ${ptype} Protocol</button>
          </div>`}
        </div>`;
      }).join('')}
    </div>`;
}

async function createProtocol(qualId, ptype) {
  try {
    const qual = await (await fetch(`/qual/${qualId}`)).json();
    const res = await fetch(`/qual/${qualId}/protocols`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        protocol_type: ptype,
        title: `${ptype} Protocol — ${qual.equipment_name || 'Equipment'}`,
      }),
    });
    const prot = await res.json();
    openProtocol(qualId, prot.id, ptype);
  } catch (e) {
    alert('Failed to create protocol: ' + e.message);
  }
}

async function openProtocol(qualId, protocolId, ptype) {
  QualState.activeProtocolId = protocolId;
  QualState.activeProtocolType = ptype;
  const content = document.getElementById('qual-detail-content');
  content.innerHTML = '<div class="qual-loading">Loading protocol…</div>';
  try {
    const [protRes, tcRes] = await Promise.all([
      fetch(`/qual/${qualId}/protocols/${protocolId}`),
      fetch(`/qual/${qualId}/protocols/${protocolId}/test-cases`),
    ]);
    const protocol = await protRes.json();
    const testCases = await tcRes.json();
    QualState.testCases[protocolId] = testCases;
    content.innerHTML = renderProtocolDetail(qualId, protocol, testCases);
  } catch (e) {
    content.innerHTML = '<div class="qual-empty">Failed to load protocol</div>';
  }
}

function renderProtocolDetail(qualId, protocol, testCases) {
  const total = testCases.length;
  const pass  = testCases.filter(t => t.status === 'pass').length;
  const fail  = testCases.filter(t => t.status === 'fail').length;
  const pend  = testCases.filter(t => t.status === 'pending').length;
  const pct   = total > 0 ? Math.round(pass / total * 100) : 0;
  const ptype = protocol.protocol_type;

  return `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap">
      <button class="btn-qual-outline" onclick="loadProtocolsPane(${qualId})" style="font-size:12px">← Protocols</button>
      <div style="flex:1">
        <div style="font-size:16px;font-weight:800;color:var(--navy)">${protocol.title}</div>
        <div style="font-size:12px;color:#888">${protocol.protocol_number || 'No number'} · Rev ${protocol.revision} · ${total} test cases</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${qualStatusBadge(protocol.status)}
        <button class="btn-qual-primary" onclick="generateTestCases(${qualId},${protocol.id},'${ptype}')">🤖 AI Generate</button>
        <button class="btn-qual-secondary" onclick="aiReviewProtocol(${qualId},${protocol.id})" style="padding:7px 14px;font-size:12px">🔍 AI Review</button>
        <button class="btn-qual-dark" onclick="exportProtocol(${qualId},${protocol.id})" style="padding:7px 14px;font-size:12px">⬇ DOCX</button>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px">
      <div class="qual-stat-card"><div class="qual-stat-icon">🧪</div><div class="qual-stat-value">${total}</div><div class="qual-stat-label">Total Tests</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">✅</div><div class="qual-stat-value" style="color:#1B5E20">${pass}</div><div class="qual-stat-label">Pass</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">❌</div><div class="qual-stat-value" style="color:#B71C1C">${fail}</div><div class="qual-stat-label">Fail</div></div>
      <div class="qual-stat-card"><div class="qual-stat-icon">⏳</div><div class="qual-stat-value" style="color:#F57F17">${pend}</div><div class="qual-stat-label">Pending</div></div>
    </div>

    <div class="qual-progress-row" style="margin-bottom:18px">
      <span class="qual-progress-label">Progress</span>
      <div class="qual-progress-bar-track"><div class="qual-progress-bar-fill" style="width:${pct}%"></div></div>
      <span class="qual-progress-pct">${pct}%</span>
    </div>

    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div style="font-size:14px;font-weight:700;color:var(--navy)">Test Cases</div>
      <button class="btn-qual-outline" onclick="addTestCaseManual(${qualId},${protocol.id},'${ptype}')" style="font-size:12px">+ Add Test Case</button>
    </div>

    <div class="qual-tc-list" id="tc-list-${protocol.id}">
      ${testCases.length ? testCases.map(tc => renderTestCaseItem(qualId, protocol.id, tc)).join('') :
        `<div class="qual-empty"><div class="qual-empty-icon">🧪</div><div class="qual-empty-text">No test cases yet. Click AI Generate to create them automatically.</div></div>`}
    </div>`;
}

function renderTestCaseItem(qualId, protocolId, tc) {
  const statusIcon = { pass: '✅', fail: '❌', na: 'N/A', pending: '⏳' }[tc.status || 'pending'] || '⏳';
  return `
    <div class="qual-tc-item" id="tc-item-${tc.id}">
      <div class="qual-tc-header" onclick="toggleTestCase(${tc.id})">
        <span class="qual-tc-id">${tc.test_id || 'TC'}</span>
        <span class="qual-tc-name">${tc.test_name}</span>
        <span class="qual-tc-section">${tc.section}</span>
        <div class="qual-tc-badge-row">
          <span class="qs-badge qs-${(tc.gmp_criticality||'gmp').toLowerCase().replace('-','').replace(' ','-')}" style="font-size:10px">${tc.gmp_criticality || 'GMP'}</span>
          <span class="qs-badge qs-${tc.status||'pending'}" style="font-size:10px">${statusIcon} ${(tc.status || 'pending').toUpperCase()}</span>
        </div>
        <span class="qual-tc-expand-icon">▼</span>
      </div>
      <div class="qual-tc-body">
        <div class="qual-tc-detail-grid">
          ${tc.objective ? `<div class="qual-tc-detail-item full-width"><label>Objective</label><p>${tc.objective}</p></div>` : ''}
          ${tc.prerequisites ? `<div class="qual-tc-detail-item full-width"><label>Prerequisites</label><p>${tc.prerequisites}</p></div>` : ''}
          ${tc.test_procedure ? `<div class="qual-tc-detail-item full-width"><label>Test Procedure</label><p>${tc.test_procedure}</p></div>` : ''}
          <div class="qual-tc-detail-item"><label>Expected Result</label><p>${tc.expected_result || '—'}</p></div>
          <div class="qual-tc-detail-item"><label>Acceptance Criteria</label><p>${tc.acceptance_criteria || '—'}</p></div>
          ${tc.regulatory_ref ? `<div class="qual-tc-detail-item"><label>Regulatory Ref</label><p>${tc.regulatory_ref}</p></div>` : ''}
          ${(tc.urs_req_ids||[]).length ? `<div class="qual-tc-detail-item"><label>URS Req IDs</label><p>${tc.urs_req_ids.join(', ')}</p></div>` : ''}
          ${(tc.risk_item_ids||[]).length ? `<div class="qual-tc-detail-item"><label>Risk Item IDs</label><p>${tc.risk_item_ids.join(', ')}</p></div>` : ''}
        </div>

        <!-- Execution panel -->
        <div class="qual-exec-panel">
          <h4>⚡ Execute Test Case</h4>
          <div class="qual-exec-grid">
            <div class="qual-form-group">
              <label>Actual Result</label>
              <textarea id="exec-actual-${tc.id}" rows="2" placeholder="Enter actual observed result…"></textarea>
            </div>
            <div class="qual-form-group">
              <label>Comments</label>
              <textarea id="exec-comments-${tc.id}" rows="2" placeholder="Any comments or observations…"></textarea>
            </div>
            <div class="qual-form-group">
              <label>Executed By</label>
              <input type="text" id="exec-by-${tc.id}" placeholder="Name" />
            </div>
            <div class="qual-form-group">
              <label>Date</label>
              <input type="date" id="exec-date-${tc.id}" value="${new Date().toISOString().split('T')[0]}" />
            </div>
            <div class="qual-form-group">
              <label>Electronic Signature</label>
              <input type="text" id="exec-sig-${tc.id}" placeholder="Name / ID" />
            </div>
          </div>
          <div style="margin-top:12px">
            <label style="font-size:11px;font-weight:700;color:#555;display:block;margin-bottom:6px">RESULT</label>
            <div class="qual-result-btns">
              <button class="qual-result-btn pass" id="rb-pass-${tc.id}" onclick="setResult(${tc.id},'pass')">✅ PASS</button>
              <button class="qual-result-btn fail" id="rb-fail-${tc.id}" onclick="setResult(${tc.id},'fail')">❌ FAIL</button>
              <button class="qual-result-btn na"   id="rb-na-${tc.id}"   onclick="setResult(${tc.id},'na')">N/A</button>
            </div>
          </div>
          <div style="display:flex;gap:8px;margin-top:12px">
            <button class="btn-qual-success" onclick="saveExecution(${qualId},${protocolId},${tc.id})">💾 Save Result</button>
            <button class="btn-qual-danger" onclick="deleteTestCase(${qualId},${protocolId},${tc.id})" style="font-size:11px">🗑️ Delete TC</button>
          </div>
        </div>
      </div>
    </div>`;
}

function toggleTestCase(tcId) {
  const item = document.getElementById(`tc-item-${tcId}`);
  item.classList.toggle('expanded');
}

let selectedResults = {};
function setResult(tcId, result) {
  selectedResults[tcId] = result;
  ['pass','fail','na'].forEach(r => {
    const btn = document.getElementById(`rb-${r}-${tcId}`);
    if (btn) btn.classList.toggle('active', r === result);
  });
}

async function saveExecution(qualId, protocolId, tcId) {
  const result = selectedResults[tcId] || 'pending';
  const payload = {
    actual_result:  document.getElementById(`exec-actual-${tcId}`)?.value || '',
    comments:       document.getElementById(`exec-comments-${tcId}`)?.value || '',
    executed_by:    document.getElementById(`exec-by-${tcId}`)?.value || '',
    executed_date:  document.getElementById(`exec-date-${tcId}`)?.value || '',
    electronic_sig: document.getElementById(`exec-sig-${tcId}`)?.value || '',
    result,
    auto_deviation: result === 'fail',
  };
  try {
    const res = await fetch(`/qual/${qualId}/protocols/${protocolId}/execute/${tcId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    // Update local status badge
    const badge = document.querySelector(`#tc-item-${tcId} .qs-badge:last-child`);
    const icon = { pass: '✅', fail: '❌', na: 'N/A', pending: '⏳' }[result] || '⏳';
    if (badge) badge.innerHTML = `${icon} ${result.toUpperCase()}`;
    const item = document.getElementById(`tc-item-${tcId}`);
    if (item) item.querySelector('.qual-tc-header').style.background = result === 'pass' ? '#f0fff4' : result === 'fail' ? '#fff5f5' : '';
    alert(result === 'pass' ? '✅ Test passed and saved!' : result === 'fail' ? '❌ Test failed. Deviation created.' : '✔ Result saved.');
  } catch (e) {
    alert('Save failed: ' + e.message);
  }
}

async function deleteTestCase(qualId, protocolId, tcId) {
  if (!confirm('Delete this test case?')) return;
  await fetch(`/qual/${qualId}/protocols/${protocolId}/test-cases/${tcId}`, { method: 'DELETE' });
  document.getElementById(`tc-item-${tcId}`)?.remove();
}

/* ── AI Generate ─────────────────────────────────────────────────────────────── */
async function generateTestCases(qualId, protocolId, ptype) {
  if (QualState.generating) return;
  QualState.generating = true;

  // Show overlay
  const overlay = document.createElement('div');
  overlay.className = 'qual-generating-overlay';
  overlay.id = 'qual-gen-overlay';
  overlay.innerHTML = `
    <div class="qual-generating-box">
      <div class="qual-generating-spinner"></div>
      <div class="qual-generating-title">🤖 Generating ${ptype} Test Cases</div>
      <div class="qual-generating-sub" id="qual-gen-sub">AI is analyzing equipment and URS requirements…</div>
      <div id="qual-gen-count" style="font-size:22px;font-weight:800;color:var(--navy);margin-top:12px">0 test cases</div>
    </div>`;
  document.body.appendChild(overlay);

  let chunkCount = 0;
  try {
    const res = await fetch(`/qual/${qualId}/protocols/${protocolId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        try {
          const ev = JSON.parse(line.slice(5).trim());
          if (ev.chunk) {
            chunkCount++;
            document.getElementById('qual-gen-sub').textContent = 'Generating comprehensive test cases…';
            document.getElementById('qual-gen-count').textContent = `${chunkCount * 5}+ characters`;
          }
          if (ev.done) {
            document.getElementById('qual-gen-count').textContent = `${ev.count || '?'} test cases generated!`;
            await new Promise(r => setTimeout(r, 800));
          }
          if (ev.error) {
            alert('Generation error: ' + ev.error);
          }
        } catch {}
      }
    }
  } catch (e) {
    alert('Generation failed: ' + e.message);
  } finally {
    QualState.generating = false;
    overlay.remove();
    openProtocol(qualId, protocolId, ptype);
  }
}

/* ── AI Review ───────────────────────────────────────────────────────────────── */
async function aiReviewProtocol(qualId, protocolId) {
  const content = document.getElementById('qual-detail-content');
  const reviewArea = document.createElement('div');
  reviewArea.innerHTML = '<div class="qual-loading" style="padding:30px">🔍 Running AI review…</div>';
  content.appendChild(reviewArea);
  try {
    const res = await fetch(`/qual/${qualId}/protocols/${protocolId}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    const r = await res.json();
    reviewArea.innerHTML = renderAIReview(r);
  } catch (e) {
    reviewArea.innerHTML = `<div class="qual-empty">Review failed: ${e.message}</div>`;
  }
}

function renderAIReview(r) {
  const rec = r.recommendation || '';
  const recClass = rec.toLowerCase().includes('approved') ? 'approved' : rec.toLowerCase().includes('major') ? 'major' : 'revision';
  return `
    <div class="qual-review-panel" style="margin-top:18px">
      <div class="qual-card-header">
        <span class="qual-card-title">🤖 AI Protocol Review</span>
      </div>
      <div class="qual-review-recommendation ${recClass}">${rec}</div>
      <div class="qual-review-scores">
        <div class="qual-review-score-card"><div class="qual-review-score-value">${r.overall_score || 0}</div><div class="qual-review-score-label">Overall Score</div></div>
        <div class="qual-review-score-card"><div class="qual-review-score-value">${r.compliance_score || 0}</div><div class="qual-review-score-label">Compliance</div></div>
        <div class="qual-review-score-card"><div class="qual-review-score-value">${r.completeness_score || 0}</div><div class="qual-review-score-label">Completeness</div></div>
        <div class="qual-review-score-card"><div class="qual-review-score-value">${r.risk_coverage_score || 0}</div><div class="qual-review-score-label">Risk Coverage</div></div>
      </div>
      ${r.executive_summary ? `<div style="padding:14px;background:#f8fbff;border-radius:8px;font-size:13px;color:#333;margin-bottom:16px;line-height:1.6">${r.executive_summary}</div>` : ''}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        ${reviewSection('✅ Strengths', r.strengths, '#E8F5E9', '#2E7D32', '✔')}
        ${reviewSection('⚠️ Missing Tests', r.missing_tests, '#FFF8E1', '#F57F17', '!')}
        ${reviewSection('📋 Improvements', r.improvements, '#E3F2FD', '#1565C0', '→')}
        ${reviewSection('🔴 Regulatory Gaps', r.regulatory_gaps, '#FFEBEE', '#B71C1C', '!')}
        ${r.duplicate_tests?.length ? reviewSection('🔄 Duplicate Tests', r.duplicate_tests, '#F3E5F5', '#6A1B9A', '≡') : ''}
      </div>
    </div>`;
}

function reviewSection(title, items, bg, color, icon) {
  if (!items?.length) return '';
  return `<div style="background:${bg};border-radius:10px;padding:14px">
    <div style="font-size:12px;font-weight:700;color:${color};margin-bottom:10px">${title}</div>
    <ul class="qual-review-list">
      ${items.map(i => `<li><span style="color:${color}">${icon}</span> ${i}</li>`).join('')}
    </ul>
  </div>`;
}

/* ── Execution Tab ───────────────────────────────────────────────────────────── */
async function loadExecutionPane(qualId) {
  const content = document.getElementById('qual-detail-content');
  content.innerHTML = '<div class="qual-loading">Loading execution status…</div>';
  try {
    const protRes = await fetch(`/qual/${qualId}/protocols`);
    const protocols = await protRes.json();
    if (!protocols.length) {
      content.innerHTML = `<div class="qual-empty"><div class="qual-empty-icon">▶️</div><div class="qual-empty-text">No protocols created yet. Create IQ/OQ/PQ protocols first.</div></div>`;
      return;
    }
    let html = '';
    for (const prot of protocols) {
      const tcRes = await fetch(`/qual/${qualId}/protocols/${prot.id}/test-cases`);
      const tcs = await tcRes.json();
      const total = tcs.length;
      const pass = tcs.filter(t => t.status === 'pass').length;
      const fail = tcs.filter(t => t.status === 'fail').length;
      const pend = tcs.filter(t => t.status === 'pending').length;
      const pct = total > 0 ? Math.round(pass / total * 100) : 0;
      html += `
        <div class="qual-card" style="margin-bottom:14px">
          <div class="qual-card-header">
            <span class="qual-card-title">${prot.protocol_type} Protocol — ${prot.title}</span>
            <button class="btn-qual-outline" onclick="openProtocol(${qualId},${prot.id},'${prot.protocol_type}')" style="font-size:12px">Execute Tests</button>
          </div>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px">
            <div class="qual-stat-card" style="padding:10px"><div class="qual-stat-value">${total}</div><div class="qual-stat-label">Total</div></div>
            <div class="qual-stat-card" style="padding:10px"><div class="qual-stat-value" style="color:#1B5E20">${pass}</div><div class="qual-stat-label">Pass</div></div>
            <div class="qual-stat-card" style="padding:10px"><div class="qual-stat-value" style="color:#B71C1C">${fail}</div><div class="qual-stat-label">Fail</div></div>
            <div class="qual-stat-card" style="padding:10px"><div class="qual-stat-value" style="color:#F57F17">${pend}</div><div class="qual-stat-label">Pending</div></div>
          </div>
          <div class="qual-progress-row">
            <span class="qual-progress-label">Pass Rate</span>
            <div class="qual-progress-bar-track"><div class="qual-progress-bar-fill" style="width:${pct}%"></div></div>
            <span class="qual-progress-pct">${pct}%</span>
          </div>
        </div>`;
    }
    content.innerHTML = html;
  } catch (e) {
    content.innerHTML = '<div class="qual-empty">Failed to load execution data</div>';
  }
}

/* ── Deviations Tab ──────────────────────────────────────────────────────────── */
async function loadDeviationsPane(qualId) {
  const content = document.getElementById('qual-detail-content');
  content.innerHTML = '<div class="qual-loading">Loading deviations…</div>';
  try {
    const res = await fetch(`/qual/${qualId}/deviations`);
    const devs = await res.json();
    content.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div style="font-size:14px;font-weight:700;color:var(--navy)">Deviations (${devs.length})</div>
        <button class="btn-qual-primary" onclick="createDeviationForm(${qualId})">+ New Deviation</button>
      </div>
      <div id="qual-dev-list">
        ${devs.length ? devs.map(d => renderDeviationItem(qualId, d)).join('') :
          `<div class="qual-empty"><div class="qual-empty-icon">✅</div><div class="qual-empty-text">No deviations recorded</div></div>`}
      </div>`;
  } catch (e) {
    content.innerHTML = '<div class="qual-empty">Failed to load deviations</div>';
  }
}

function renderDeviationItem(qualId, d) {
  const impactClass = d.impact === 'Critical' ? 'critical' : '';
  const statusClass = d.status === 'closed' ? 'closed' : '';
  return `
    <div class="qual-dev-item ${impactClass} ${statusClass}">
      <div class="qual-dev-header">
        <span class="qual-dev-number">${d.deviation_number}</span>
        <span class="qual-dev-title">${d.title}</span>
        <span class="qs-badge ${d.status === 'open' ? 'qs-in-progress' : 'qs-completed'}">${d.status?.toUpperCase()}</span>
        <span class="qs-badge ${d.impact === 'Critical' ? 'qs-fail' : d.impact === 'Major' ? 'qs-in-progress' : 'qs-draft'}">${d.impact}</span>
      </div>
      <div class="qual-dev-meta">
        ${d.description ? `<div style="margin-bottom:4px;color:#555">${d.description}</div>` : ''}
        <div>Raised by: ${d.raised_by || '—'} on ${d.raised_date || '—'}</div>
        ${d.corrective_action ? `<div style="margin-top:4px"><strong>CAPA:</strong> ${d.corrective_action}</div>` : ''}
      </div>
    </div>`;
}

async function createDeviationForm(qualId) {
  const title = prompt('Deviation Title:');
  if (!title) return;
  const desc = prompt('Description:');
  const impact = prompt('Impact (Critical/Major/Minor):', 'Minor');
  const raisedBy = prompt('Raised By:');
  try {
    const res = await fetch(`/qual/${qualId}/deviations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description: desc, impact, raised_by: raisedBy, raised_date: new Date().toISOString().split('T')[0] }),
    });
    const dev = await res.json();
    loadDeviationsPane(qualId);
  } catch (e) {
    alert('Failed: ' + e.message);
  }
}

/* ── Traceability Tab ────────────────────────────────────────────────────────── */
async function loadTraceabilityPane(qualId) {
  const content = document.getElementById('qual-detail-content');
  content.innerHTML = '<div class="qual-loading">Building traceability matrix…</div>';
  try {
    const res = await fetch(`/qual/${qualId}/traceability`);
    const matrix = await res.json();
    content.innerHTML = renderTraceabilityPane(qualId, matrix);
  } catch (e) {
    content.innerHTML = '<div class="qual-empty">Failed to load traceability matrix</div>';
  }
}

function renderTraceabilityPane(qualId, matrix) {
  const rows = matrix.matrix_rows || [];
  const ursCov = matrix.urs_coverage || {};
  const riskCov = matrix.risk_coverage || {};
  const ursTotal = matrix.urs_requirements?.length || 0;
  const riskTotal = matrix.risk_items?.length || 0;
  const ursCovPct = ursTotal > 0 ? Math.round(Object.keys(ursCov).length / ursTotal * 100) : 0;
  const riskCovPct = riskTotal > 0 ? Math.round(Object.keys(riskCov).length / riskTotal * 100) : 0;

  return `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div style="font-size:14px;font-weight:700;color:var(--navy)">🔗 Auto-Generated Traceability Matrix</div>
      <button class="btn-qual-primary" onclick="exportTraceability(${qualId})">⬇ Export DOCX</button>
    </div>

    <div class="qual-trace-summary">
      <div class="qual-trace-stat"><div class="qual-trace-stat-value">${rows.length}</div><div class="qual-trace-stat-label">Test Cases</div></div>
      <div class="qual-trace-stat"><div class="qual-trace-stat-value">${ursTotal}</div><div class="qual-trace-stat-label">URS Requirements</div></div>
      <div class="qual-trace-stat"><div class="qual-trace-stat-value" style="color:${ursCovPct>=80?'#1B5E20':'#F57F17'}">${ursCovPct}%</div><div class="qual-trace-stat-label">URS Coverage</div></div>
      <div class="qual-trace-stat"><div class="qual-trace-stat-value">${riskTotal}</div><div class="qual-trace-stat-label">Risk Items</div></div>
      <div class="qual-trace-stat"><div class="qual-trace-stat-value" style="color:${riskCovPct>=80?'#1B5E20':'#F57F17'}">${riskCovPct}%</div><div class="qual-trace-stat-label">Risk Coverage</div></div>
    </div>

    <div class="qual-card">
      <div class="qual-card-header"><span class="qual-card-title">Test Case Traceability</span></div>
      <div class="qual-trace-table-wrap">
        <table class="qual-table">
          <thead><tr><th>Test ID</th><th>Test Name</th><th>Section</th><th>URS Req IDs</th><th>Risk IDs</th><th>Status</th></tr></thead>
          <tbody>
            ${rows.map(r => `
              <tr>
                <td><strong>${r.test_id}</strong></td>
                <td style="font-size:12px">${r.test_name || ''}</td>
                <td style="font-size:11px;color:#888">${r.section || ''}</td>
                <td style="font-size:11px">${(r.urs_req_ids||[]).join(', ') || '—'}</td>
                <td style="font-size:11px">${(r.risk_item_ids||[]).join(', ') || '—'}</td>
                <td>${qualResultBadge(r.status)}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>`;
}

/* ── Approvals Tab ───────────────────────────────────────────────────────────── */
async function loadApprovalsPane(qualId) {
  const content = document.getElementById('qual-detail-content');
  content.innerHTML = '<div class="qual-loading">Loading approval trail…</div>';
  try {
    const res = await fetch(`/qual/${qualId}/approval`);
    const trail = await res.json();
    content.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div style="font-size:14px;font-weight:700;color:var(--navy)">Approval Trail</div>
        <button class="btn-qual-primary" onclick="addApprovalForm(${qualId})">+ Add Approval</button>
      </div>
      <div class="qual-timeline">
        ${trail.length ? trail.map(e => `
          <div class="qual-timeline-item">
            <div class="qual-timeline-dot"></div>
            <div class="qual-timeline-content">
              <div class="qual-timeline-action">${e.action}</div>
              <div class="qual-timeline-meta">${e.performed_by} · ${e.role || ''} · ${e.created_at?.split('T')[0] || ''}</div>
              ${e.comments ? `<div style="font-size:12px;color:#555;margin-top:4px">${e.comments}</div>` : ''}
            </div>
          </div>`).join('') :
          '<div class="qual-empty" style="padding:20px">No approval entries yet</div>'}
      </div>`;
  } catch (e) {
    content.innerHTML = '<div class="qual-empty">Failed to load</div>';
  }
}

async function addApprovalForm(qualId) {
  const action = prompt('Action:', 'Submitted for Review');
  if (!action) return;
  const performedBy = prompt('Performed By:');
  if (!performedBy) return;
  const role = prompt('Role:', 'Validation Engineer');
  const comments = prompt('Comments:', '');
  try {
    await fetch(`/qual/${qualId}/approval`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, performed_by: performedBy, role, comments }),
    });
    loadApprovalsPane(qualId);
  } catch (e) {
    alert('Failed: ' + e.message);
  }
}

/* ── Version History Tab ─────────────────────────────────────────────────────── */
async function loadVersionsPane(qualId) {
  const content = document.getElementById('qual-detail-content');
  content.innerHTML = '<div class="qual-loading">Loading version history…</div>';
  try {
    const res = await fetch(`/qual/${qualId}/versions`);
    const versions = await res.json();
    content.innerHTML = `
      <div style="font-size:14px;font-weight:700;color:var(--navy);margin-bottom:16px">Version History</div>
      ${versions.length ? `
      <div class="qual-table-wrapper">
        <table class="qual-table">
          <thead><tr><th>Version</th><th>Type</th><th>Revision</th><th>Status</th><th>Tests</th><th>Pass</th><th>Fail</th><th>Created By</th><th>Date</th></tr></thead>
          <tbody>
            ${versions.map(v => `
              <tr>
                <td><strong>${v.version}</strong></td>
                <td>${v.protocol_type}</td>
                <td>Rev ${v.revision}</td>
                <td>${qualStatusBadge(v.status)}</td>
                <td>${v.test_count}</td>
                <td style="color:#1B5E20;font-weight:600">${v.pass_count}</td>
                <td style="color:#B71C1C;font-weight:600">${v.fail_count}</td>
                <td style="font-size:12px">${v.created_by || '—'}</td>
                <td style="font-size:11px;color:#888">${v.created_at?.split('T')[0] || ''}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>` : '<div class="qual-empty"><div class="qual-empty-icon">📜</div><div class="qual-empty-text">No version snapshots yet</div></div>'}`;
  } catch (e) {
    content.innerHTML = '<div class="qual-empty">Failed to load</div>';
  }
}

/* ── Export ──────────────────────────────────────────────────────────────────── */
function exportProtocol(qualId, protocolId) {
  window.location.href = `/qual/${qualId}/protocols/${protocolId}/export/docx`;
}

function exportTraceability(qualId) {
  window.location.href = `/qual/${qualId}/traceability/export/docx`;
}

/* ── Delete ──────────────────────────────────────────────────────────────────── */
async function deleteQualification(qualId) {
  if (!confirm('Delete this qualification and all its protocols, test cases, and execution data?')) return;
  try {
    await fetch(`/qual/${qualId}`, { method: 'DELETE' });
    qualShowList();
  } catch (e) {
    alert('Delete failed: ' + e.message);
  }
}

/* ── Add Test Case Manual ────────────────────────────────────────────────────── */
async function addTestCaseManual(qualId, protocolId, ptype) {
  const testName = prompt('Test Case Name:');
  if (!testName) return;
  const section = prompt('Section:', 'General');
  const prefix = ptype === 'IQ' ? 'IQ-TC' : ptype === 'OQ' ? 'OQ-TC' : 'PQ-TC';
  const existing = QualState.testCases[protocolId] || [];
  const nextNum = (existing.length + 1).toString().padStart(3, '0');
  const payload = {
    test_id: `${prefix}-${nextNum}`,
    test_name: testName,
    section: section || 'General',
    source: 'manual',
  };
  try {
    const res = await fetch(`/qual/${qualId}/protocols/${protocolId}/test-cases/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const tc = await res.json();
    const list = document.getElementById(`tc-list-${protocolId}`);
    if (list) {
      const item = document.createElement('div');
      item.innerHTML = renderTestCaseItem(qualId, protocolId, tc);
      list.appendChild(item.firstElementChild);
    }
  } catch (e) {
    alert('Failed: ' + e.message);
  }
}

/* ── Helpers ─────────────────────────────────────────────────────────────────── */
function qualStatusBadge(status) {
  const map = {
    draft: ['qs-draft', 'Draft'],
    in_progress: ['qs-in-progress', 'In Progress'],
    completed: ['qs-completed', 'Completed'],
    completed_with_deviations: ['qs-in-progress', 'Completed w/ Devs'],
    approved: ['qs-approved', '✓ Approved'],
    under_review: ['qs-under-review', 'Under Review'],
    pending_approval: ['qs-pending-approval', 'Pending Approval'],
    not_started: ['qs-not-started', 'Not Started'],
    closed: ['qs-completed', 'Closed'],
    obsolete: ['qs-not-started', 'Obsolete'],
  };
  const [cls, label] = map[status] || ['qs-draft', status || 'Unknown'];
  return `<span class="qs-badge ${cls}">${label}</span>`;
}

function qualPhasePill(phase, status) {
  const phaseClass = phase.toLowerCase();
  const statusClass = status === 'completed' || status === 'approved' ? 'completed' :
    status === 'in_progress' ? 'in-progress' :
    status === 'fail' || status === 'completed_with_deviations' ? 'fail' : 'not-started';
  return `<span class="qual-phase-pill ${phaseClass} ${statusClass}">${phase}</span>`;
}

function qualResultBadge(status) {
  const map = { pass: 'qs-pass ✅ PASS', fail: 'qs-fail ❌ FAIL', na: 'qs-na N/A', pending: 'qs-pending ⏳ PENDING' };
  const v = map[status] || 'qs-pending ⏳ PENDING';
  const [cls, ...rest] = v.split(' ');
  return `<span class="qs-badge ${cls}">${rest.join(' ')}</span>`;
}

/* ── Sidebar collapse ────────────────────────────────────────────────────────── */
function toggleQualSection() {
  const items = document.getElementById('qual-nav-items');
  const btn = document.getElementById('qual-collapse-btn');
  if (items) {
    const collapsed = items.style.display === 'none';
    items.style.display = collapsed ? '' : 'none';
    if (btn) btn.textContent = collapsed ? '▲' : '▼';
  }
}

/* ── Global exports ──────────────────────────────────────────────────────────── */
window.initQual               = initQual;
window.qualShowDashboard      = qualShowDashboard;
window.qualShowList           = qualShowList;
window.qualShowNew            = qualShowNew;
window.qualShowDetail         = qualShowDetail;
window.qualDetailTab          = qualDetailTab;
window.toggleQualSection      = toggleQualSection;
window.openProtocol           = openProtocol;
window.createProtocol         = createProtocol;
window.generateTestCases      = generateTestCases;
window.aiReviewProtocol       = aiReviewProtocol;
window.saveExecution          = saveExecution;
window.deleteTestCase         = deleteTestCase;
window.toggleTestCase         = toggleTestCase;
window.setResult              = setResult;
window.loadDeviationsPane     = loadDeviationsPane;
window.loadTraceabilityPane   = loadTraceabilityPane;
window.loadApprovalsPane      = loadApprovalsPane;
window.loadVersionsPane       = loadVersionsPane;
window.exportProtocol         = exportProtocol;
window.exportTraceability     = exportTraceability;
window.deleteQualification    = deleteQualification;
window.filterQualList         = filterQualList;
window.addApprovalForm        = addApprovalForm;
window.createDeviationForm    = createDeviationForm;
window.addTestCaseManual      = addTestCaseManual;
