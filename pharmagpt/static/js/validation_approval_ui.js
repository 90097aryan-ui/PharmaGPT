/**
 * static/js/validation_approval_ui.js — the ONE approval-page component shared
 * by URS and Qualification (IQ/OQ/PQ). Backed by services/validation_approval.py.
 *
 * Usage: ValidationApproval.render(containerEl, { base: "/urs" | "/qual", id, onChanged })
 *
 * The page lists the seven mandatory signatories with name, designation,
 * e-signature record, date and pending/current/completed status. Every action
 * goes through the reusable e-signature dialog (esignature_dialog.js); the
 * server alone decides who may act — buttons are shown by document status and
 * a server refusal is surfaced as-is, never worked around here.
 */
(function () {
  "use strict";

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  const STATE_LABEL = { completed: "Completed", current: "Awaiting signature", pending: "Pending" };
  const REVIEW = ["under_review", "technical_review", "qa_review", "validation_review", "final_approval"];

  async function postAction(cfg, body) {
    const res = await fetch(`${cfg.base}/${cfg.id}/approval`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Server returned HTTP ${res.status}`);
    return data;
  }

  function sign(cfg, payload, meaning) {
    if (!window.PharmaESign) throw new Error("Electronic Signature dialog failed to load");
    window.PharmaESign.open({
      meaning,
      onConfirm: async ({ password, meaning: m, reason }) => {
        await postAction(cfg, { ...payload, password, meaning: m, reason,
                                comments: payload.action === "Rejected" ? reason : (payload.comments || "") });
        if (cfg.onChanged) await cfg.onChanged();
        else render(cfg.container, cfg);
      },
    });
  }

  function actionButtons(cfg, page) {
    const out = [];
    const status = page.status;
    const attr = (o) => esc(JSON.stringify(o));
    if (status === "draft") {
      out.push(`<button class="va-btn va-primary" data-va='${attr({ action: "Submitted for Review", meaning: "Created" })}'>Submit for Review</button>`);
    }
    if (REVIEW.includes(status)) {
      page.signatories.filter(s => s.status === "current" && s.stage === status).forEach(s => {
        out.push(`<button class="va-btn va-primary" data-va='${attr({ action: "Sign Off", signatory: s.key, meaning: status === "final_approval" ? "Approved" : "Reviewed" })}'>Sign as ${esc(s.label)}</button>`);
      });
      out.push(`<button class="va-btn va-danger" data-va='${attr({ action: "Rejected", meaning: "Rejected" })}'>Reject</button>`);
    }
    if (status === "approved") {
      out.push(`<button class="va-btn va-primary" data-va='${attr({ action: "Make Effective", meaning: "Released" })}'>Make Effective</button>`);
      out.push(`<button class="va-btn va-danger" data-va='${attr({ action: "Rejected", meaning: "Rejected" })}'>Send back for revision</button>`);
    }
    if (status === "effective") {
      out.push(`<button class="va-btn" data-va='${attr({ action: "Obsolete", meaning: "Cancelled" })}'>Mark Obsolete</button>`);
    }
    if (status === "pending_approval") {
      out.push(`<button class="va-btn va-danger" data-va='${attr({ action: "Rejected", meaning: "Rejected" })}'>Reject to Draft</button>`);
    }
    return out.join("");
  }

  async function render(container, cfg) {
    cfg.container = container;
    container.innerHTML = '<div class="va-loading">Loading approval page…</div>';
    let page;
    try {
      const res = await fetch(`${cfg.base}/${cfg.id}/approval/signatories`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `HTTP ${res.status}`);
      page = await res.json();
    } catch (e) {
      container.innerHTML = `<div class="va-error">Couldn't load the approval page: ${esc(e.message)}</div>`;
      return;
    }

    const legacyNote = page.legacy_approval
      ? '<div class="va-note">Approved under the pre-standard workflow — no signatory ledger exists for this document.</div>' : "";
    const stuckNote = page.status === "pending_approval" || (REVIEW.includes(page.status) && page.completed_count === 0 && page.superseded_count === 0)
      ? '<div class="va-note">This document entered review before the standard workflow. Reject it to Draft and resubmit to collect the required signatures.</div>' : "";

    container.innerHTML = `
      <style>
        .va-table{width:100%;border-collapse:collapse;font-size:13px}
        .va-table th,.va-table td{padding:8px 10px;border-bottom:1px solid var(--border,#e2e8f0);text-align:left;vertical-align:top}
        .va-chip{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}
        .va-completed{background:#dcfce7;color:#166534}.va-current{background:#fef3c7;color:#92400e}.va-pending{background:#e2e8f0;color:#475569}
        .va-btn{padding:7px 14px;border-radius:6px;border:1px solid var(--border,#cbd5e1);background:transparent;cursor:pointer;margin:0 8px 8px 0;font-size:13px}
        .va-primary{background:var(--navy,#1e3a5f);color:#fff;border-color:transparent}.va-danger{color:#b91c1c;border-color:#b91c1c}
        .va-note{background:#fef3c7;border-radius:6px;padding:8px 12px;font-size:12px;margin-bottom:12px}
        .va-sig{font-size:11px;color:#64748b;word-break:break-all}
      </style>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <strong>Approval signatories</strong>
        <span>${page.completed_count} of ${page.mandatory_count} signed</span>
      </div>
      ${legacyNote}${stuckNote}
      <table class="va-table">
        <thead><tr><th>Signatory</th><th>Designation</th><th>Name</th><th>E-signature record</th><th>Date</th><th>Status</th></tr></thead>
        <tbody>${page.signatories.map(s => `
          <tr>
            <td><strong>${esc(s.label)}</strong></td>
            <td>${esc(s.designation)}</td>
            <td>${esc(s.signer_name) || "—"}</td>
            <td>${s.signature ? `${esc(s.signature.meaning)} · #${esc(s.signature.id)}<div class="va-sig">${esc((s.signature.hash || "").slice(0, 16))}…</div>` : "—"}</td>
            <td>${s.signed_at ? esc(String(s.signed_at).replace("T", " ").slice(0, 16)) : "—"}</td>
            <td><span class="va-chip va-${esc(s.status)}">${STATE_LABEL[s.status] || esc(s.status)}</span></td>
          </tr>`).join("")}
        </tbody>
      </table>
      <div style="margin-top:14px" id="va-actions">${actionButtons(cfg, page)}</div>
      <div class="va-error" id="va-action-error" role="alert" style="color:#b91c1c;font-size:13px"></div>`;

    container.querySelectorAll("[data-va]").forEach(btn => {
      btn.addEventListener("click", () => {
        const payload = JSON.parse(btn.getAttribute("data-va"));
        try { sign(cfg, payload, payload.meaning); }
        catch (e) { container.querySelector("#va-action-error").textContent = e.message; }
      });
    });
  }

  window.ValidationApproval = { render };
})();
