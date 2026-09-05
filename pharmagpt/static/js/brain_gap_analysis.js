// static/js/brain_gap_analysis.js — Yuktav Brain: Regulatory Gap Analysis V1
// (PharmaPilot workspace, second surface beside Compliance Check).
//
// Thin presentation layer over the already-verified POST /brain/gap-analysis
// (pharmagpt/services/brain_gap_analysis.py) — no new backend logic here.
// Reuses qms_common.js's qmsPostJSON/qmsToast/qmsBadge and window.activeProject
// exactly as static/js/brain_compare.js already does. brain_compare.js is not
// imported from or modified by this file — its own small escHtml/scopeBadge/
// categoryLabel helpers are duplicated here on purpose (frozen-surface
// isolation for Brain Comparison V1; see PROJECT_MEMORY/DECISIONS.md).
//
// The backend owns every tenant/security decision (company_id is resolved
// there from the authenticated session — see routes/brain.py). This module
// never reads, stores, or sends a company_id, role, tenant_id, or scope
// value; it only sends { question, project_id }.
//
// Every value in a rendered result — requirement text, client evidence
// summaries, gaps, overall summary, and evidence-reference metadata — comes
// from Gemini output, retrieved document text, or the user's own question,
// and is treated as untrusted: escHtml() is applied before any such value is
// placed into innerHTML. coverage_status and evidence scope are the only
// values interpolated unescaped, and only after being checked against a
// fixed allow-list first (never raw model/user text).

(function () {
  'use strict';

  function escHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  var COVERAGE_STATUSES = ['COVERED', 'PARTIALLY_COVERED', 'NOT_COVERED', 'INSUFFICIENT_EVIDENCE'];

  function coverageBadge(status) {
    if (COVERAGE_STATUSES.indexOf(status) === -1) return '';
    return qmsBadge(status.replace(/_/g, ' '));
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

  function confidenceBadge(confidence) {
    if (typeof confidence !== 'number' || !isFinite(confidence)) return '';
    return qmsBadge(Math.round(confidence * 100) + '% confidence');
  }

  function renderReferences(refs) {
    if (!Array.isArray(refs) || !refs.length) return '';
    var items = refs.map(function (r) {
      var meta = [];
      var cat = categoryLabel(r.content_category);
      if (cat) meta.push(escHtml(cat));
      if (r.source_authority) meta.push(escHtml(r.source_authority));
      if (r.source_reference) meta.push(escHtml(r.source_reference));
      var metaLine = meta.length
        ? '<div class="qms-panel-item-meta">' + meta.join(' &middot; ') + '</div>' : '';
      return (
        '<div class="qms-panel-item">' +
          '<div>' +
            '<div>' + escHtml(r.name || 'Untitled source') + '</div>' +
            metaLine +
          '</div>' +
          scopeBadge(r.scope) +
        '</div>'
      );
    }).join('');
    return (
      '<div class="qms-section-card">' +
        '<h3>Evidence References (' + refs.length + ')</h3>' +
        items +
      '</div>'
    );
  }

  function renderRequirement(item) {
    var gapBlock = item.gap
      ? '<p><strong>Gap</strong></p><p>' + escHtml(item.gap) + '</p>'
      : '';
    return (
      '<div class="qms-panel-item" style="flex-direction:column;align-items:stretch;gap:6px">' +
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">' +
          '<p style="margin:0"><strong>' + escHtml(item.requirement) + '</strong></p>' +
          coverageBadge(item.coverage_status) +
        '</div>' +
        '<p style="margin:0"><strong>Client Evidence</strong></p>' +
        '<p style="margin:0">' + escHtml(item.client_evidence_summary || '(none identified)') + '</p>' +
        gapBlock +
        confidenceBadge(item.confidence) +
      '</div>'
    );
  }

  function renderResult(result) {
    var box = document.getElementById('gap-analysis-result');
    if (!box) return;

    var requirements = Array.isArray(result.requirements) ? result.requirements : [];
    var overallSummary = result.overall_summary || '';

    var requirementsBlock = requirements.length
      ? '<div class="qms-section-card"><h3>Requirements (' + requirements.length + ')</h3>' +
          requirements.map(renderRequirement).join('') +
        '</div>'
      : '<div class="qms-section-card"><p class="qms-panel-item-meta">No applicable regulatory ' +
          'requirements could be identified from the available evidence.</p></div>';

    box.innerHTML = (
      '<div class="qms-section-card">' +
        '<p><strong>Overall Summary</strong></p>' +
        '<p>' + escHtml(overallSummary || '(none provided)') + '</p>' +
      '</div>' +
      requirementsBlock +
      renderReferences(result.evidence_references)
    );
    box.hidden = false;
  }

  async function run() {
    var input = document.getElementById('gap-analysis-question');
    var btn = document.getElementById('gap-analysis-run-btn');
    var resultBox = document.getElementById('gap-analysis-result');
    var question = (input && input.value ? input.value : '').trim();

    if (!window.activeProject) {
      qmsToast('Select or create a project before running a Regulatory Gap Analysis.');
      return;
    }
    if (!question) {
      qmsToast('Enter a regulatory topic or question first.');
      return;
    }

    if (resultBox) resultBox.hidden = true;
    var originalText = btn.innerHTML;
    btn.disabled = true;
    btn.textContent = 'Running…';

    try {
      // company_id is never sent — the backend resolves it from the
      // authenticated session (routes/brain.py::gap_analysis()).
      var result = await qmsPostJSON('/brain/gap-analysis', {
        question: question,
        project_id: window.activeProject.id,
      });
      renderResult(result);
    } catch (e) {
      qmsToast('Regulatory Gap Analysis failed: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  }

  window.BrainGapAnalysis = { run: run };
})();
