/*
 * investigation_case.js — reusable Investigation Case component (architecture
 * refactor: Workflow vs. Investigation separation).
 *
 * Answers "what work has been done to find the root cause" — evidence, SOP
 * review, interviews, timeline, AI assistance, root cause, and the CAPA
 * handoff summary. Deliberately generic: mount() takes (recordType, recordId,
 * baseRoutePrefix) so any business module can reuse it later (CAPA/OOS/OOT/
 * Complaint/Audit Finding/Supplier/Validation investigations) by pointing at
 * its own owning blueprint's `/investigation/*` sub-routes — no change to
 * this file. Every sub-tab is freely navigable; there is no workflow
 * transition inside the Investigation Case itself.
 *
 * Reuses qms_common.js's qmsFetch/qmsPostJSON/qmsPutJSON/qmsToast/qmsBadge
 * and the existing generic qmsRenderAttachments panel for the Attachments tab.
 */

window.InvestigationCase = (function () {
  const TABS = [
    { key: "overview", label: "Overview" },
    { key: "evidence", label: "Evidence" },
    { key: "documents", label: "Documents" },
    { key: "tasks", label: "Tasks" },
    { key: "sop", label: "SOP Review" },
    { key: "kb", label: "Knowledge Base" },
    { key: "interviews", label: "Interviews" },
    { key: "timeline", label: "Timeline" },
    { key: "ai", label: "AI Assistant" },
    { key: "rootcause", label: "Root Cause" },
    { key: "risk", label: "Risk" },
    { key: "attachments", label: "Attachments" },
    { key: "summary", label: "Summary" },
  ];

  const _state = {};

  function _s(containerId) {
    return _state[containerId];
  }

  function _base(containerId) {
    const s = _s(containerId);
    return `${s.baseRoutePrefix}/${s.recordId}/investigation`;
  }

  function mount(containerId, recordType, recordId, baseRoutePrefix) {
    _state[containerId] = { recordType, recordId, baseRoutePrefix, activeTab: "overview" };
    _render(containerId);
  }

  function switchTab(containerId, tab) {
    _state[containerId].activeTab = tab;
    _render(containerId);
  }

  async function _render(containerId) {
    const el = document.getElementById(containerId);
    const s = _s(containerId);
    el.innerHTML = `
      <div class="ic-tabs">
        ${TABS.map(t => `<button class="ic-tab ${t.key === s.activeTab ? "active" : ""}" onclick="InvestigationCase.switchTab('${containerId}','${t.key}')">${t.label}</button>`).join("")}
      </div>
      <div class="ic-tab-body" id="${containerId}-body"><div class="qms-loading"><div class="qms-spinner"></div> Loading…</div></div>
    `;
    const bodyId = `${containerId}-body`;
    try {
      await _renderTab[s.activeTab](containerId, bodyId);
    } catch (e) {
      document.getElementById(bodyId).innerHTML = `<div class="qms-empty"><p>Failed to load: ${e.message}</p></div>`;
    }
  }

  function _refresh(containerId) {
    _render(containerId);
  }

  // ── Overview ────────────────────────────────────────────────────────────

  async function _renderOverview(containerId, bodyId) {
    const dash = await qmsFetch(`${_base(containerId)}/dashboard`);
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Investigation Case Overview</h3>
        <p style="font-size:12.5px;color:var(--text-muted)">
          Evidence, SOP review, interviews, timeline, AI assistance, and root cause for this record —
          freely navigable, re-runnable, and independent of the Lifecycle workflow.
        </p>
        <div class="qms-stats-grid">
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.investigation_progress_pct}%</div><div>Investigation Progress</div></div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.evidence_score}%</div><div>Evidence Score</div></div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.interviews_completed}/${dash.interviews_total}</div><div>Interviews Complete</div></div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.outstanding_tasks}</div><div>Outstanding Tasks</div></div>
        </div>
      </div>
    `;
  }

  // ── Evidence Dashboard (rules-based — refinement #4; Part 10 dashboard) ───

  function _renderAiRecommendations(rec) {
    if (!rec) return `<p class="qms-panel-item-meta">No AI Assistant run yet — recommendations appear here after one is run.</p>`;
    const groups = [
      ["Missing evidence", rec.missing_evidence], ["Missing SOP review", rec.missing_sop_review],
      ["Missing interviews", rec.missing_interviews], ["Missing calibration", rec.missing_calibration],
      ["Missing PM records", rec.missing_pm], ["Missing training records", rec.missing_training],
      ["Contradictions", rec.contradictions], ["Recommended next steps", rec.recommended_next_steps],
    ].filter(([, items]) => items && items.length);
    return `
      <p class="qms-panel-item-meta">${rec.source} — generated ${rec.generated_at || "—"}</p>
      ${groups.length ? groups.map(([label, items]) => `<p><strong>${label}:</strong> ${items.join("; ")}</p>`).join("")
        : `<p class="qms-panel-item-meta">No gaps flagged by the most recent run.</p>`}
    `;
  }

  async function _renderEvidenceDashboard(containerId, bodyId) {
    const dash = await qmsFetch(`${_base(containerId)}/dashboard`);
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Evidence Dashboard</h3>
        <p style="font-size:11.5px;color:var(--text-muted)">${dash.evidence_score_basis}</p>
        <div class="qms-stats-grid">
          <div class="qms-stat-card ${dash.evidence_score < 50 ? "critical" : dash.evidence_score < 80 ? "warning" : "success"}">
            <div class="qms-stat-value">${dash.evidence_score}%</div><div>Evidence Score</div>
          </div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.investigation_progress_pct}%</div><div>Investigation Progress</div></div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.document_completeness_pct}%</div><div>Document Completeness</div></div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.sop_review_completeness_pct}%</div><div>SOP Review Completeness</div></div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.interview_completeness_pct}%</div><div>Interview Completeness</div></div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.timeline_completeness_pct}%</div><div>Timeline Completeness</div></div>
          <div class="qms-stat-card ${dash.outstanding_tasks ? "warning" : "success"}"><div class="qms-stat-value">${dash.outstanding_tasks}</div><div>Outstanding Tasks</div></div>
        </div>
        ${dash.missing_evidence_categories.length ? `<p><strong>Missing evidence categories:</strong> ${dash.missing_evidence_categories.join(", ")}</p>` : ""}
        ${dash.missing_timeline_event_types.length ? `<p><strong>Missing timeline event types:</strong> ${dash.missing_timeline_event_types.join(", ")}</p>` : ""}
        ${dash.sop_reviews_requiring_clarification ? `<p><strong>${dash.sop_reviews_requiring_clarification}</strong> SOP review(s) marked "Requires Clarification".</p>` : ""}
      </div>
      <div class="qms-section-card">
        <h3>AI Recommendations</h3>
        <p style="font-size:11px;color:var(--text-muted)">Advisory only — never folded into the deterministic scores above (Evidence Score/Progress are computed by fixed rules, never by AI).</p>
        ${_renderAiRecommendations(dash.latest_ai_recommendations)}
      </div>
    `;
  }

  // ── Documents (evidence records, review status) ───────────────────────────

  const EVIDENCE_CATEGORIES = ["BMR", "BPR", "SOP", "Calibration Certificate", "PM Record", "Cleaning Record",
    "Environmental Monitoring", "Equipment Log", "Validation Report", "Change Control", "Previous Deviation",
    "Previous CAPA", "Training Record", "Photo", "Video", "Other"];
  const REVIEW_STATUSES = ["Pending", "Reviewed", "Not Applicable", "Flagged"];

  // ── Shared attachment picker (Evidence / Interviews / Tasks) ─────────────
  // Reuses the deviation's existing /qms/deviation/<id>/attachments endpoint —
  // no per-entity upload route. Uploads once against the deviation, then the
  // caller links the returned attachment_id into its own row.
  async function _attachmentPickerHtml(containerId, fieldId) {
    const s = _s(containerId);
    let attachments = [];
    try { attachments = await qmsFetch(`/qms/${s.recordType}/${s.recordId}/attachments`); } catch (e) { /* best-effort */ }
    const options = attachments.map(a => `<option value="${a.id}">${a.original_name} (${a.uploaded_by || "—"}, ${a.created_at})</option>`).join("");
    return `
      <div class="form-field span-2">
        <label>Evidence Attachment (optional)</label>
        <select id="${fieldId}"><option value="">— none —</option>${options}</select>
        <div style="margin-top:6px">
          <input type="file" id="${fieldId}-file" style="font-size:12px" />
          <button type="button" class="btn-secondary" style="padding:5px 10px;font-size:11.5px" onclick="InvestigationCase._uploadAndLink('${containerId}','${fieldId}')">Upload New</button>
        </div>
      </div>
    `;
  }

  async function _uploadAndLink(containerId, fieldId) {
    const s = _s(containerId);
    const fileInput = document.getElementById(`${fieldId}-file`);
    if (!fileInput || !fileInput.files.length) { qmsToast("Choose a file first"); return; }
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    try {
      const attachment = await qmsFetch(`/qms/${s.recordType}/${s.recordId}/attachments`, { method: "POST", body: fd });
      const select = document.getElementById(fieldId);
      const opt = document.createElement("option");
      opt.value = attachment.id;
      opt.text = `${attachment.original_name} (${attachment.uploaded_by || "—"}, ${attachment.created_at})`;
      select.add(opt);
      select.value = attachment.id;
      qmsToast("File uploaded and linked");
    } catch (e) {
      qmsToast("Upload failed: " + e.message);
    }
  }

  function _attachmentIdValue(fieldId) {
    const el = document.getElementById(fieldId);
    return el && el.value ? Number(el.value) : null;
  }

  async function _renderDocuments(containerId, bodyId) {
    const [items, attachmentsHtml] = await Promise.all([
      qmsFetch(`${_base(containerId)}/evidence`), _attachmentPickerHtml(containerId, `${bodyId}-attach`),
    ]);
    const attachmentNames = {};
    try {
      (await qmsFetch(`/qms/${_s(containerId).recordType}/${_s(containerId).recordId}/attachments`))
        .forEach(a => { attachmentNames[a.id] = a; });
    } catch (e) { /* best-effort join */ }
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Add Evidence / Document</h3>
        <div class="form-grid">
          <div class="form-field"><label>Type</label><select id="${bodyId}-cat">${EVIDENCE_CATEGORIES.map(c => `<option>${c}</option>`).join("")}</select></div>
          <div class="form-field"><label>Review Status</label><select id="${bodyId}-status">${REVIEW_STATUSES.map(s => `<option>${s}</option>`).join("")}</select></div>
          <div class="form-field"><label>Source</label><input type="text" id="${bodyId}-source" placeholder="e.g. LIMS export, QA Department" /></div>
          <div class="form-field"><label>Version</label><input type="text" id="${bodyId}-version" placeholder="e.g. Rev 2" /></div>
          <div class="form-field span-2"><label>Description / Comments</label><input type="text" id="${bodyId}-desc" placeholder="e.g. Batch Manufacturing Record BMR-2026-014" /></div>
          ${attachmentsHtml}
        </div>
        <div class="qms-form-actions"><button class="btn-primary" onclick="InvestigationCase._addEvidence('${containerId}','${bodyId}')">Add</button></div>
      </div>
      ${items.length ? `
        <table class="qms-table">
          <thead><tr><th>Type</th><th>Source</th><th>Uploaded By</th><th>Upload Date</th><th>Version</th><th>Status</th><th>Comments</th></tr></thead>
          <tbody>${items.map(i => {
            const att = i.attachment_id ? attachmentNames[i.attachment_id] : null;
            return `<tr><td>${i.category}</td><td>${i.source || "—"}</td><td>${att ? (att.uploaded_by || "—") : "—"}</td><td>${att ? att.created_at : "—"}</td><td>${i.version || "—"}</td><td>${qmsBadge(i.review_status)}</td><td>${i.description || "—"}</td></tr>`;
          }).join("")}</tbody>
        </table>` : `<div class="qms-empty"><p>No evidence recorded yet.</p></div>`}
    `;
  }

  async function _addEvidence(containerId, bodyId) {
    const data = {
      category: document.getElementById(`${bodyId}-cat`).value,
      review_status: document.getElementById(`${bodyId}-status`).value,
      description: document.getElementById(`${bodyId}-desc`).value.trim(),
      source: document.getElementById(`${bodyId}-source`).value.trim(),
      version: document.getElementById(`${bodyId}-version`).value.trim(),
      attachment_id: _attachmentIdValue(`${bodyId}-attach`),
    };
    try {
      await qmsPostJSON(`${_base(containerId)}/evidence`, data);
      qmsToast("Evidence added");
      _renderDocuments(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  // ── Investigation Tasks (Phase 2 Part 1) ──────────────────────────────────

  const TASK_PRIORITIES = ["Low", "Medium", "High", "Critical"];
  const TASK_STATUSES = ["Pending", "In Progress", "Completed", "Cancelled"];

  async function _renderTasks(containerId, bodyId) {
    const [items, attachmentsHtml] = await Promise.all([
      qmsFetch(`${_base(containerId)}/tasks`), _attachmentPickerHtml(containerId, `${bodyId}-attach`),
    ]);
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Add Investigation Task</h3>
        <p style="font-size:11.5px;color:var(--text-muted)">Investigative activities — not a Workflow step or CAPA action. Completing a task never advances the Lifecycle.</p>
        <div class="form-grid">
          <div class="form-field span-2"><label>Task Title</label><input type="text" id="${bodyId}-title" /></div>
          <div class="form-field span-2"><label>Description</label><textarea id="${bodyId}-desc"></textarea></div>
          <div class="form-field"><label>Assigned User</label><input type="text" id="${bodyId}-assignee" /></div>
          <div class="form-field"><label>Department</label><input type="text" id="${bodyId}-dept" /></div>
          <div class="form-field"><label>Priority</label><select id="${bodyId}-priority">${TASK_PRIORITIES.map(p => `<option ${p === "Medium" ? "selected" : ""}>${p}</option>`).join("")}</select></div>
          <div class="form-field"><label>Due Date</label><input type="date" id="${bodyId}-due" /></div>
          <div class="form-field span-2"><label>Comments</label><textarea id="${bodyId}-comments"></textarea></div>
          ${attachmentsHtml}
        </div>
        <div class="qms-form-actions"><button class="btn-primary" onclick="InvestigationCase._addTask('${containerId}','${bodyId}')">Add Task</button></div>
      </div>
      ${items.length ? `
        <table class="qms-table">
          <thead><tr><th>Title</th><th>Assigned</th><th>Department</th><th>Priority</th><th>Due Date</th><th>Status</th><th>Completed</th></tr></thead>
          <tbody>${items.map(t => `<tr>
            <td>${t.title}${t.description ? `<div class="qms-panel-item-meta">${t.description}</div>` : ""}</td>
            <td>${t.assigned_user || "—"}</td><td>${t.department || "—"}</td><td>${qmsBadge(t.priority)}</td>
            <td>${t.due_date || "—"}</td>
            <td><select onchange="InvestigationCase._updateTaskStatus('${containerId}','${bodyId}',${t.id},this.value)">${TASK_STATUSES.map(s => `<option ${s === t.status ? "selected" : ""}>${s}</option>`).join("")}</select></td>
            <td>${t.completion_date || "—"}</td>
          </tr>`).join("")}</tbody>
        </table>` : `<div class="qms-empty"><p>No investigation tasks yet.</p></div>`}
    `;
  }

  async function _addTask(containerId, bodyId) {
    const data = {
      title: document.getElementById(`${bodyId}-title`).value.trim(),
      description: document.getElementById(`${bodyId}-desc`).value.trim(),
      assigned_user: document.getElementById(`${bodyId}-assignee`).value.trim(),
      department: document.getElementById(`${bodyId}-dept`).value.trim(),
      priority: document.getElementById(`${bodyId}-priority`).value,
      due_date: document.getElementById(`${bodyId}-due`).value,
      comments: document.getElementById(`${bodyId}-comments`).value.trim(),
      evidence_attachment_id: _attachmentIdValue(`${bodyId}-attach`),
    };
    if (!data.title) { qmsToast("Task title is required"); return; }
    try {
      await qmsPostJSON(`${_base(containerId)}/tasks`, data);
      qmsToast("Task added");
      _renderTasks(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  async function _updateTaskStatus(containerId, bodyId, taskId, status) {
    try {
      await qmsPutJSON(`${_base(containerId)}/tasks/${taskId}`, { status });
      qmsToast("Task updated");
      _renderTasks(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  // ── SOP Review ─────────────────────────────────────────────────────────────

  const SOP_REVIEW_STATUSES = ["Pending", "Reviewed", "Not Applicable", "Requires Clarification"];

  async function _renderSopReview(containerId, bodyId) {
    const items = await qmsFetch(`${_base(containerId)}/sop-review`);
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Add Applicable SOP / Specification</h3>
        <div class="form-grid">
          <div class="form-field"><label>Document Reference</label><input type="text" id="${bodyId}-ref" placeholder="e.g. SOP-QA-014" /></div>
          <div class="form-field"><label>Version</label><input type="text" id="${bodyId}-ver" /></div>
          <div class="form-field"><label>Effective Date</label><input type="date" id="${bodyId}-eff" /></div>
          <div class="form-field"><label>Review Status</label><select id="${bodyId}-status">${SOP_REVIEW_STATUSES.map(s => `<option>${s}</option>`).join("")}</select></div>
          <div class="form-field span-2"><label>Relevant Section</label><input type="text" id="${bodyId}-section" /></div>
        </div>
        <div class="qms-form-actions"><button class="btn-primary" onclick="InvestigationCase._addSopReview('${containerId}','${bodyId}')">Add</button></div>
      </div>
      ${items.length ? `
        <table class="qms-table">
          <thead><tr><th>Document</th><th>Version</th><th>Effective Date</th><th>Section</th><th>Status</th></tr></thead>
          <tbody>${items.map(i => `<tr><td>${i.doc_reference}</td><td>${i.version || "—"}</td><td>${i.effective_date || "—"}</td><td>${i.relevant_section || "—"}</td><td>${qmsBadge(i.review_status)}</td></tr>`).join("")}</tbody>
        </table>` : `<div class="qms-empty"><p>No SOPs reviewed yet.</p></div>`}
    `;
  }

  async function _addSopReview(containerId, bodyId) {
    const data = {
      doc_reference: document.getElementById(`${bodyId}-ref`).value.trim(),
      version: document.getElementById(`${bodyId}-ver`).value.trim(),
      effective_date: document.getElementById(`${bodyId}-eff`).value,
      relevant_section: document.getElementById(`${bodyId}-section`).value.trim(),
      review_status: document.getElementById(`${bodyId}-status`).value,
    };
    if (!data.doc_reference) { qmsToast("Document reference is required"); return; }
    try {
      await qmsPostJSON(`${_base(containerId)}/sop-review`, data);
      qmsToast("SOP review entry added");
      _renderSopReview(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  // ── Knowledge Base Integration (Phase 2 Part 3) ───────────────────────────
  // Read-only reference lists — nothing here is persisted until the
  // investigator explicitly accepts a suggestion into SOP Review.

  async function _renderKnowledgeBase(containerId, bodyId) {
    const kb = await qmsFetch(`${_base(containerId)}/knowledge-base`);
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Suggested SOPs / Work Instructions / Validation Protocols / Risk Assessments</h3>
        <p style="font-size:11.5px;color:var(--text-muted)">Auto-retrieved from the Knowledge Base by relevance to this deviation — review and accept into SOP Review, or dismiss.</p>
        ${kb.kb_suggestions.length ? kb.kb_suggestions.map((s, i) => `
          <div class="qms-panel-item">
            <div><strong>${s.doc_reference}</strong><div class="qms-panel-item-meta">${s.source_type}</div></div>
            <button class="btn-secondary" style="padding:5px 10px;font-size:11.5px" onclick="InvestigationCase._acceptKbSuggestion('${containerId}','${bodyId}',${i})">Add to SOP Review</button>
          </div>
        `).join("") : `<div class="qms-empty"><p>No Knowledge Base matches found for this deviation.</p></div>`}
      </div>
      <div class="qms-section-card">
        <h3>Previous Deviations</h3>
        ${kb.previous_deviations.length ? kb.previous_deviations.map(d => `
          <div class="qms-panel-item"><div><strong>${d.deviation_number}</strong> — ${d.title}<div class="qms-panel-item-meta">${d.product || ""} ${d.equipment || ""} ${d.department || ""} · ${qmsBadge(d.status)}</div></div></div>
        `).join("") : `<div class="qms-empty"><p>No related previous deviations found.</p></div>`}
      </div>
      <div class="qms-section-card">
        <h3>Previous CAPAs</h3>
        ${kb.previous_capas.length ? kb.previous_capas.map(c => `
          <div class="qms-panel-item"><div><strong>${c.capa_number}</strong> — ${c.title}<div class="qms-panel-item-meta">${c.department || ""} · ${qmsBadge(c.status)}</div></div></div>
        `).join("") : `<div class="qms-empty"><p>No related previous CAPAs found.</p></div>`}
      </div>
      <div class="qms-section-card">
        <h3>Equipment History</h3>
        ${kb.equipment_history.length ? kb.equipment_history.map(e => `
          <div class="qms-panel-item"><div><strong>${e.name}</strong><div class="qms-panel-item-meta">${e.equipment_code || ""} ${e.manufacturer || ""}</div></div></div>
        `).join("") : `<div class="qms-empty"><p>No matching equipment records found.</p></div>`}
      </div>
    `;
    _state[containerId]._kbSuggestions = kb.kb_suggestions;
  }

  async function _acceptKbSuggestion(containerId, bodyId, index) {
    const s = (_state[containerId]._kbSuggestions || [])[index];
    if (!s) return;
    try {
      await qmsPostJSON(`${_base(containerId)}/knowledge-base/accept-sop`, { doc_reference: s.doc_reference });
      qmsToast("Added to SOP Review");
      _renderKnowledgeBase(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  // ── Interviews ───────────────────────────────────────────────────────────

  const INTERVIEW_ROLES = ["Production", "QA", "Engineering", "Maintenance", "Warehouse", "Validation", "QC", "Microbiology"];

  async function _renderInterviews(containerId, bodyId) {
    const [items, attachmentsHtml] = await Promise.all([
      qmsFetch(`${_base(containerId)}/interviews`), _attachmentPickerHtml(containerId, `${bodyId}-attach`),
    ]);
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Record Interview</h3>
        <div class="form-grid">
          <div class="form-field"><label>Interviewee Name (Person)</label><input type="text" id="${bodyId}-name" /></div>
          <div class="form-field"><label>Role / Department</label><select id="${bodyId}-role">${INTERVIEW_ROLES.map(r => `<option>${r}</option>`).join("")}</select></div>
          <div class="form-field"><label>Interview Date</label><input type="date" id="${bodyId}-date" /></div>
          <div class="form-field"><label>Status</label><select id="${bodyId}-status"><option>Scheduled</option><option>Completed</option><option>Pending</option></select></div>
          <div class="form-field span-2"><label>Questions (one per line)</label><textarea id="${bodyId}-questions"></textarea></div>
          <div class="form-field span-2"><label>Answers (one per line)</label><textarea id="${bodyId}-answers"></textarea></div>
          <div class="form-field span-2"><label>Observations</label><textarea id="${bodyId}-obs"></textarea></div>
          <div class="form-field span-2"><label>Investigator Notes</label><textarea id="${bodyId}-notes"></textarea></div>
          ${attachmentsHtml}
        </div>
        <div class="qms-form-actions"><button class="btn-primary" onclick="InvestigationCase._addInterview('${containerId}','${bodyId}')">Save</button></div>
      </div>
      ${items.length ? `
        <table class="qms-table">
          <thead><tr><th>Person</th><th>Role</th><th>Date</th><th>Status</th><th>Observations</th><th>Notes</th></tr></thead>
          <tbody>${items.map(i => `<tr><td>${i.interviewee_name}</td><td>${i.interviewee_role || "—"}</td><td>${i.interview_date || "—"}</td><td>${qmsBadge(i.status)}</td><td>${i.observation || "—"}</td><td>${i.notes || "—"}</td></tr>`).join("")}</tbody>
        </table>` : `<div class="qms-empty"><p>No interviews recorded yet.</p></div>`}
    `;
  }

  async function _addInterview(containerId, bodyId) {
    const data = {
      interviewee_name: document.getElementById(`${bodyId}-name`).value.trim(),
      interviewee_role: document.getElementById(`${bodyId}-role`).value,
      interview_date: document.getElementById(`${bodyId}-date`).value,
      status: document.getElementById(`${bodyId}-status`).value,
      questions: document.getElementById(`${bodyId}-questions`).value.split("\n").map(s => s.trim()).filter(Boolean),
      answers: document.getElementById(`${bodyId}-answers`).value.split("\n").map(s => s.trim()).filter(Boolean),
      observation: document.getElementById(`${bodyId}-obs`).value.trim(),
      notes: document.getElementById(`${bodyId}-notes`).value.trim(),
      attachment_id: _attachmentIdValue(`${bodyId}-attach`),
    };
    if (!data.interviewee_name) { qmsToast("Interviewee name is required"); return; }
    try {
      await qmsPostJSON(`${_base(containerId)}/interviews`, data);
      qmsToast("Interview recorded");
      _renderInterviews(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  // ── Timeline ─────────────────────────────────────────────────────────────

  const TIMELINE_EVENT_TYPES = ["Batch", "Machine", "QA", "Maintenance", "Sampling", "Testing", "Deviation", "CAPA"];
  const TIMELINE_SOURCES = ["manual", "automatic", "ai"];

  async function _renderTimeline(containerId, bodyId) {
    const items = await qmsFetch(`${_base(containerId)}/timeline`);
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Add Timeline Event</h3>
        <div class="form-grid">
          <div class="form-field"><label>Event Type</label><select id="${bodyId}-type">${TIMELINE_EVENT_TYPES.map(t => `<option>${t}</option>`).join("")}</select></div>
          <div class="form-field"><label>Date/Time</label><input type="datetime-local" id="${bodyId}-dt" /></div>
          <div class="form-field"><label>Source</label><select id="${bodyId}-source">${TIMELINE_SOURCES.map(s => `<option>${s}</option>`).join("")}</select></div>
          <div class="form-field span-2"><label>Description</label><input type="text" id="${bodyId}-desc" /></div>
        </div>
        <div class="qms-form-actions"><button class="btn-primary" onclick="InvestigationCase._addTimelineEvent('${containerId}','${bodyId}')">Add</button></div>
      </div>
      ${items.length ? `
        <table class="qms-table">
          <thead><tr><th>Date/Time</th><th>Type</th><th>Source</th><th>Description</th></tr></thead>
          <tbody>${items.map(i => `<tr><td>${i.event_datetime || "—"}</td><td>${qmsBadge(i.event_type)}</td><td>${i.source || "manual"}</td><td>${i.description || "—"}</td></tr>`).join("")}</tbody>
        </table>` : `<div class="qms-empty"><p>No timeline events recorded yet.</p></div>`}
    `;
  }

  async function _addTimelineEvent(containerId, bodyId) {
    const data = {
      event_type: document.getElementById(`${bodyId}-type`).value,
      event_datetime: document.getElementById(`${bodyId}-dt`).value,
      source: document.getElementById(`${bodyId}-source`).value,
      description: document.getElementById(`${bodyId}-desc`).value.trim(),
    };
    try {
      await qmsPostJSON(`${_base(containerId)}/timeline`, data);
      qmsToast("Timeline event added");
      _renderTimeline(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  // ── AI Assistant (interactive) / AI Report Generation (refinement #5) ────

  async function _renderAI(containerId, bodyId) {
    const history = await qmsFetch(`${_base(containerId)}/ai/history`);
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>AI Investigation Assistant</h3>
        <p style="font-size:12.5px;color:var(--text-muted)">Interactive, ad-hoc analysis of the evidence gathered so far — run any number of times, never advances the workflow.</p>
        <div class="form-field"><label>Question (optional)</label><input type="text" id="${bodyId}-question" placeholder="e.g. What does the calibration record suggest?" /></div>
        <div class="qms-form-actions">
          <button class="btn-primary" onclick="InvestigationCase._runAssistant('${containerId}','${bodyId}')"><span class='icon' data-lucide='sparkles'></span> Run AI Assistant</button>
          <button class="btn-secondary" onclick="InvestigationCase._runReport('${containerId}','${bodyId}')">Generate AI Report</button>
        </div>
      </div>
      <div class="qms-section-card">
        <h3>AI Run History</h3>
        ${history.length ? history.map(r => {
          const reportVersion = r.mode === "report_generation"
            ? history.filter(h => h.mode === "report_generation" && h.created_at <= r.created_at).length : null;
          const gapGroups = [
            ["Missing evidence", r.output.missing_evidence], ["Missing SOP review", r.output.missing_sop_review],
            ["Missing interviews", r.output.missing_interviews], ["Missing calibration", r.output.missing_calibration],
            ["Missing PM records", r.output.missing_pm], ["Missing training records", r.output.missing_training],
            ["Contradictions", r.output.contradictions],
          ].filter(([, items]) => items && items.length);
          return `
          <div class="qms-panel-item" style="flex-direction:column;align-items:stretch">
            <div><strong>${r.mode === "assistant" ? "Assistant" : `Report Generation (v${reportVersion})`}</strong> — ${r.run_type} — ${qmsBadge(r.confidence != null ? Math.round(r.confidence * 100) + "% confidence" : "n/a")}</div>
            <div class="qms-panel-item-meta">Model: ${r.model || "—"} · Prompt v${r.prompt_version || "—"} · ${r.processing_duration_ms || 0}ms · by ${r.generated_by || "—"} · ${r.created_at} · ${(r.evidence_references || []).length} evidence reference(s) (traceability)</div>
            ${gapGroups.length ? gapGroups.map(([label, items]) => `<p style="font-size:12px"><strong>${label}:</strong> ${items.join("; ")}</p>`).join("") : ""}
            <pre style="white-space:pre-wrap;font-size:11.5px;background:var(--bg);padding:8px;border-radius:6px">${JSON.stringify(r.output, null, 2)}</pre>
          </div>
        `;
        }).join("") : `<div class="qms-empty"><p>No AI runs yet.</p></div>`}
      </div>
    `;
  }

  async function _runAssistant(containerId, bodyId) {
    try {
      await qmsPostJSON(`${_base(containerId)}/ai/assistant`, { question: document.getElementById(`${bodyId}-question`).value.trim() });
      qmsToast("AI Assistant run complete");
      _renderAI(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  async function _runReport(containerId, bodyId) {
    try {
      await qmsPostJSON(`${_base(containerId)}/ai/report`, {});
      qmsToast("AI Report generated");
      _renderAI(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  // ── Root Cause (Possible -> Probable -> Confirmed, refinement #6) ────────

  async function _renderRootCause(containerId, bodyId) {
    const rc = (await qmsFetch(`${_base(containerId)}/root-cause`)) || {};
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Possible Cause</h3>
        <p style="font-size:11.5px;color:var(--text-muted)">Initial hypothesis — AI-suggested or manually entered.</p>
        <div class="form-grid">
          <div class="form-field span-2"><label>Possible Cause</label><textarea id="${bodyId}-possible">${rc.possible_cause || ""}</textarea></div>
          <div class="form-field"><label>Source</label><select id="${bodyId}-possible-source"><option value="manual" ${rc.possible_cause_source === "manual" ? "selected" : ""}>Manual</option><option value="ai" ${rc.possible_cause_source === "ai" ? "selected" : ""}>AI</option></select></div>
        </div>
      </div>
      <div class="qms-section-card">
        <h3>Probable Cause</h3>
        <p style="font-size:11.5px;color:var(--text-muted)">The investigator's working hypothesis, refined with evidence.</p>
        <div class="form-grid">
          <div class="form-field span-2"><label>Probable Cause</label><textarea id="${bodyId}-probable">${rc.probable_cause || ""}</textarea></div>
          <div class="form-field span-2"><label>Rationale</label><textarea id="${bodyId}-rationale">${rc.probable_cause_rationale || ""}</textarea></div>
          <div class="form-field"><label>Confidence Level</label><input type="text" id="${bodyId}-confidence" value="${rc.confidence_level || ""}" placeholder="Low / Medium / High" /></div>
        </div>
      </div>
      <div class="qms-section-card">
        <h3>Confirmed Root Cause</h3>
        <p style="font-size:11.5px;color:var(--text-muted)">The final, QA-confirmed root cause.</p>
        <div class="form-field span-2"><label>Confirmed Root Cause</label><textarea id="${bodyId}-confirmed">${rc.confirmed_root_cause || ""}</textarea></div>
      </div>
      <div class="qms-form-actions"><button class="btn-primary" onclick="InvestigationCase._saveRootCause('${containerId}','${bodyId}')">Save</button></div>
    `;
  }

  async function _saveRootCause(containerId, bodyId) {
    const data = {
      possible_cause: document.getElementById(`${bodyId}-possible`).value.trim(),
      possible_cause_source: document.getElementById(`${bodyId}-possible-source`).value,
      probable_cause: document.getElementById(`${bodyId}-probable`).value.trim(),
      probable_cause_rationale: document.getElementById(`${bodyId}-rationale`).value.trim(),
      confidence_level: document.getElementById(`${bodyId}-confidence`).value.trim(),
      confirmed_root_cause: document.getElementById(`${bodyId}-confirmed`).value.trim(),
    };
    const sig = (window.PharmaAuth && window.PharmaAuth.getUser()) || {};
    if (data.confirmed_root_cause) {
      data.confirmed_by = sig.display_name || sig.email || "";
      data.confirmed_at = new Date().toISOString();
    }
    try {
      await qmsPutJSON(`${_base(containerId)}/root-cause`, data);
      qmsToast("Root cause saved");
      _renderRootCause(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  // ── Risk (cross-reference to the existing Risk module) ───────────────────

  async function _renderRisk(containerId, bodyId) {
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Risk Assessment</h3>
        <p style="font-size:12.5px;color:var(--text-muted)">
          Risk assessments for this investigation are managed in the Risk module, not duplicated here.
        </p>
        <button class="btn-secondary" onclick="document.getElementById('nav-risk') && document.getElementById('nav-risk').click()">Open Risk Module</button>
      </div>
    `;
  }

  // ── Attachments (reuses the existing generic qms_common.js panel) ────────

  async function _renderAttachmentsTab(containerId, bodyId) {
    const s = _s(containerId);
    document.getElementById(bodyId).innerHTML = `<div id="${bodyId}-attachments"></div>`;
    qmsRenderAttachments(`${bodyId}-attachments`, s.recordType, s.recordId);
  }

  // ── Summary (finalized CAPA handoff, refinement #7) ───────────────────────

  async function _renderSummary(containerId, bodyId) {
    const [summary, dash, rootCause] = await Promise.all([
      qmsFetch(`${_base(containerId)}/summary`).then(s => s || {}),
      qmsFetch(`${_base(containerId)}/dashboard`),
      qmsFetch(`${_base(containerId)}/root-cause`).then(r => r || {}),
    ]);
    const isFinalized = !!summary.finalized_at;
    document.getElementById(bodyId).innerHTML = `
      <div class="qms-section-card">
        <h3>Investigation Summary — Reference Data</h3>
        <p style="font-size:11.5px;color:var(--text-muted)">Auto-populated from the Evidence Dashboard and Root Cause — read-only, part of the CAPA handoff record.</p>
        <div class="qms-stats-grid">
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.document_completeness_pct}%</div><div>Evidence Reviewed</div></div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.sop_review_completeness_pct}%</div><div>Documents Reviewed</div></div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.interviews_completed}/${dash.interviews_total}</div><div>Interviews Completed</div></div>
          <div class="qms-stat-card"><div class="qms-stat-value">${dash.timeline_completeness_pct}%</div><div>Timeline Summary</div></div>
        </div>
        <p><strong>Root Cause:</strong> ${rootCause.confirmed_root_cause || rootCause.probable_cause || rootCause.possible_cause || "Not yet determined"}</p>
      </div>
      <div class="qms-section-card">
        <h3>Investigation Summary</h3>
        <p style="font-size:12.5px;color:var(--text-muted)">The formal handoff record into CAPA — replaces one-shot AI suggestions with an auditable summary.</p>
        <div class="form-grid">
          <div class="form-field span-2"><label>Summary</label><textarea id="${bodyId}-text" ${isFinalized ? "disabled" : ""}>${summary.summary_text || ""}</textarea></div>
          <div class="form-field span-2"><label>Key Findings (one per line)</label><textarea id="${bodyId}-findings" ${isFinalized ? "disabled" : ""}>${(summary.key_findings || []).join("\n")}</textarea></div>
          <div class="form-field span-2"><label>Open Questions (one per line)</label><textarea id="${bodyId}-openq" ${isFinalized ? "disabled" : ""}>${(summary.open_questions || []).join("\n")}</textarea></div>
          <div class="form-field span-2"><label>Recommended CAPA Actions (one per line)</label><textarea id="${bodyId}-actions" ${isFinalized ? "disabled" : ""}>${(summary.recommended_capa_actions || []).join("\n")}</textarea></div>
        </div>
        ${isFinalized
          ? `<p class="qms-panel-item-meta">Finalized by ${summary.finalized_by} on ${summary.finalized_at}</p>
             <div class="qms-form-actions"><button class="btn-primary" onclick="InvestigationCase._createCapaFromSummary('${containerId}')">Create CAPA</button></div>`
          : `<div class="qms-form-actions"><button class="btn-primary" onclick="InvestigationCase._finalizeSummary('${containerId}','${bodyId}')">Finalize Summary</button></div>`}
      </div>
    `;
  }

  async function _finalizeSummary(containerId, bodyId) {
    const data = {
      summary_text: document.getElementById(`${bodyId}-text`).value.trim(),
      key_findings: document.getElementById(`${bodyId}-findings`).value.split("\n").map(s => s.trim()).filter(Boolean),
      open_questions: document.getElementById(`${bodyId}-openq`).value.split("\n").map(s => s.trim()).filter(Boolean),
      recommended_capa_actions: document.getElementById(`${bodyId}-actions`).value.split("\n").map(s => s.trim()).filter(Boolean),
    };
    try {
      await qmsPutJSON(`${_base(containerId)}/summary`, data);
      qmsToast("Investigation Summary finalized");
      _renderSummary(containerId, bodyId);
    } catch (e) {
      qmsToast("Failed: " + e.message);
    }
  }

  async function _createCapaFromSummary(containerId) {
    const s = _s(containerId);
    if (s.recordType !== "deviation") {
      qmsToast("CAPA creation from summary is only wired for deviations right now");
      return;
    }
    try {
      const summary = await qmsFetch(`${_base(containerId)}/summary`);
      const rootCause = await qmsFetch(`${_base(containerId)}/root-cause`);
      const dev = await qmsFetch(`/qms/deviations/${s.recordId}`);
      const capa = await qmsPostJSON("/qms/capa", {
        title: `CAPA for ${dev.deviation_number}`,
        capa_source: "Deviation",
        source_reference: dev.deviation_number,
        department: dev.department,
        problem_statement: summary.summary_text || "",
        root_cause: (rootCause && (rootCause.confirmed_root_cause || rootCause.probable_cause)) || "",
      });
      for (const action of (summary.recommended_capa_actions || [])) {
        await qmsPostJSON(`/qms/capa/${capa.id}/actions`, { action_type: "Corrective", description: action });
      }
      await qmsPostJSON(`/qms/deviations/${s.recordId}/link-capa`, { capa_id: capa.id });
      qmsToast(`Created and linked ${capa.capa_number}`);
    } catch (e) {
      qmsToast("Failed to create CAPA: " + e.message);
    }
  }

  const _renderTab = {
    overview: _renderOverview,
    evidence: _renderEvidenceDashboard,
    documents: _renderDocuments,
    tasks: _renderTasks,
    sop: _renderSopReview,
    kb: _renderKnowledgeBase,
    interviews: _renderInterviews,
    timeline: _renderTimeline,
    ai: _renderAI,
    rootcause: _renderRootCause,
    risk: _renderRisk,
    attachments: _renderAttachmentsTab,
    summary: _renderSummary,
  };

  return {
    mount, switchTab,
    _addEvidence, _addSopReview, _addInterview, _addTimelineEvent,
    _addTask, _updateTaskStatus, _acceptKbSuggestion, _uploadAndLink,
    _runAssistant, _runReport, _saveRootCause,
    _finalizeSummary, _createCapaFromSummary,
  };
})();
