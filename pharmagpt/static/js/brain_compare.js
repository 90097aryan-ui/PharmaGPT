// static/js/brain_compare.js — Yuktav Brain: Compliance Check UI (PharmaPilot workspace).
//
// Thin presentation layer over the already-verified POST /brain/compare
// (pharmagpt/services/brain_comparison.py) — no new backend logic here.
// Reuses qms_common.js's qmsPostJSON/qmsToast/qmsBadge and window.activeProject
// (the same project-context global chat.js already reads) rather than
// introducing a second fetch/auth/project-state mechanism.
//
// The backend owns every tenant/security decision (company_id is resolved
// there from the authenticated session — see routes/brain.py). This module
// never reads, stores, or sends a company_id, role, or scope value; it only
// sends { question, project_id }.

(function () {
  'use strict';

  function escHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function categoryLabel(category) {
    if (category === 'regulatory_source') return 'Regulatory Source';
    if (category === 'yuktav_interpretation') return 'Yuktav Interpretation';
    return '';
  }

  function scopeBadge(scope) {
    if (scope !== 'Global' && scope !== 'Client') return '';
    return qmsBadge(scope);
  }

  function renderReferences(refs) {
    if (!Array.isArray(refs) || !refs.length) return '';
    const items = refs.map(function (r) {
      const meta = [];
      const cat = categoryLabel(r.content_category);
      if (cat) meta.push(escHtml(cat));
      if (r.source_authority) meta.push(escHtml(r.source_authority));
      if (r.source_reference) meta.push(escHtml(r.source_reference));
      const metaLine = meta.length
        ? `<div class="qms-panel-item-meta">${meta.join(' &middot; ')}</div>` : '';
      return `
        <div class="qms-panel-item">
          <div>
            <div>${escHtml(r.name || 'Untitled source')}</div>
            ${metaLine}
          </div>
          ${scopeBadge(r.scope)}
        </div>`;
    }).join('');
    return `
      <div class="qms-section-card">
        <h3>Evidence References (${refs.length})</h3>
        ${items}
      </div>`;
  }

  function renderResult(result) {
    const box = document.getElementById('brain-compare-result');
    if (!box) return;

    const status = result.compliance_status;
    const hasStatus = status === 'PASS' || status === 'WARNING' || status === 'FAIL';
    // null/absent compliance_status means the Brain could not establish a
    // defensible conclusion — never reinterpret that as a negative or
    // positive result (see PROJECT_MEMORY/DECISIONS.md).
    const statusLine = hasStatus
      ? `<p><strong>Compliance Status:</strong> ${qmsBadge(status)}</p>`
      : `<p><strong>Compliance Status:</strong> <span class="qms-panel-item-meta">Insufficient evidence to determine compliance</span></p>`;

    const confidence = result.confidence;
    const confidenceValid = typeof confidence === 'number' && isFinite(confidence);
    const confidenceLine = confidenceValid
      ? `<p><strong>Confidence:</strong> ${qmsBadge(Math.round(confidence * 100) + '% confidence')}</p>`
      : '';

    const gaps = Array.isArray(result.gaps) ? result.gaps : [];
    const gapsBlock = gaps.length
      ? `<div class="qms-section-card"><h3>Gaps</h3><ul>${gaps.map(function (g) {
          return `<li>${escHtml(g)}</li>`;
        }).join('')}</ul></div>`
      : '';

    box.innerHTML = `
      <div class="qms-section-card">
        ${statusLine}
        ${confidenceLine}
        <p><strong>Regulatory Requirement</strong></p>
        <p>${escHtml(result.regulatory_requirement || '(none identified)')}</p>
        <p><strong>Client Evidence</strong></p>
        <p>${escHtml(result.client_evidence_summary || '(none identified)')}</p>
        <p><strong>Conclusion</strong></p>
        <p>${escHtml(result.conclusion || '')}</p>
      </div>
      ${gapsBlock}
      ${renderReferences(result.evidence_references)}
    `;
    box.hidden = false;
  }

  async function run() {
    const input = document.getElementById('brain-compare-question');
    const btn = document.getElementById('brain-compare-run-btn');
    const resultBox = document.getElementById('brain-compare-result');
    const question = (input && input.value ? input.value : '').trim();

    if (!window.activeProject) {
      qmsToast('Select or create a project before running a Compliance Check.');
      return;
    }
    if (!question) {
      qmsToast('Enter a compliance question or regulatory topic first.');
      return;
    }

    if (resultBox) resultBox.hidden = true;
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.textContent = 'Running…';

    try {
      // company_id is never sent — the backend resolves it from the
      // authenticated session (routes/brain.py::compare()).
      const result = await qmsPostJSON('/brain/compare', {
        question: question,
        project_id: window.activeProject.id,
      });
      renderResult(result);
    } catch (e) {
      qmsToast('Compliance Check failed: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  }

  window.BrainCompare = { run: run };
})();
