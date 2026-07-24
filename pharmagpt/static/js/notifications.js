/* notifications.js — Phase 5: Notification center.
 *
 * "Display existing events only. No notification engine." Every item
 * rendered here comes from a pre-existing endpoint's existing fields —
 * qms/dashboard's due_for_review/overdue_capas/overdue_changes lists, plus
 * status-filtered list endpoints that already accept a `status` query
 * param (urs.py, qual.py, risk.py, qms_documents.py all confirmed by
 * reading routes/*.py). No new backend route, no new field, no polling
 * engine beyond a plain client-side setInterval re-fetch of the same
 * endpoints.
 *
 * "Project Assigned" (named in the original spec) is intentionally NOT
 * rendered: no assignment/ownership-change tracking exists anywhere in
 * the schema, and fabricating events for it would violate "existing
 * events only." This is a deliberate, documented omission — see
 * PHASE_5_ENTERPRISE_UX_REPORT.md.
 */

(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function safeJson(res) {
    return res.ok ? res.json().catch(() => null) : Promise.resolve(null);
  }

  function openCapa(id) { if (window.showView) window.showView("view-qms-capa"); if (window.qmsCapaOpenDetail) window.qmsCapaOpenDetail(id); }
  function openChange(id) { if (window.showView) window.showView("view-qms-change-control"); if (window.qmsCCOpenDetail) window.qmsCCOpenDetail(id); }
  function openDoc(id) { if (window.showView) window.showView("view-qms-documents"); if (window.qmsDocOpenDetail) window.qmsDocOpenDetail(id); }
  function openUrs(id) { if (window.openURS) window.openURS(id); }
  function openQual(id) { if (window.showView) window.showView("view-qual"); if (window.qualShowDetail) window.qualShowDetail(id); }
  function openRisk(id) { if (window.openAssessment) window.openAssessment(id); }

  async function fetchAll() {
    const [qmsDash, pendingDocs, ursReview, qualReview, riskReview] = await Promise.all([
      fetch("/qms/dashboard").then(safeJson).catch(() => null),
      fetch("/qms/documents?status=pending_approval").then(safeJson).catch(() => null),
      fetch("/urs/?status=under_review").then(safeJson).catch(() => null),
      fetch("/qual/?status=under_review").then(safeJson).catch(() => null),
      fetch("/risk/assessments?status=in_review").then(safeJson).catch(() => null),
    ]);

    const approvalPending = [];
    const reviewPending = [];
    const documentPublished = [];

    if (qmsDash) {
      (qmsDash.capa && qmsDash.capa.overdue_capas || []).forEach(c =>
        approvalPending.push({ title: c.title, meta: `CAPA ${c.capa_number} · overdue`, open: () => openCapa(c.id) }));
      (qmsDash.change_control && qmsDash.change_control.overdue_changes || []).forEach(c =>
        approvalPending.push({ title: c.title, meta: `Change Control ${c.cc_number} · overdue`, open: () => openChange(c.id) }));
      (qmsDash.documents && qmsDash.documents.due_for_review || []).forEach(d =>
        reviewPending.push({ title: d.title, meta: `${d.doc_number} · review due ${d.review_date || "—"}`, open: () => openDoc(d.id) }));
      (qmsDash.documents && qmsDash.documents.recent || []).forEach(d => {
        if (d.status === "effective" || d.status === "released") {
          documentPublished.push({ title: d.title, meta: `${d.doc_number} · ${d.status}`, open: () => openDoc(d.id) });
        }
      });
    }

    (Array.isArray(pendingDocs) ? pendingDocs : []).forEach(d =>
      approvalPending.push({ title: d.title, meta: `Document ${d.doc_number} · pending approval`, open: () => openDoc(d.id) }));

    (Array.isArray(ursReview) ? ursReview : []).forEach(u =>
      reviewPending.push({ title: u.title, meta: `URS · ${u.equipment_name || "under review"}`, open: () => openUrs(u.id) }));

    (Array.isArray(qualReview) ? qualReview : []).forEach(q =>
      reviewPending.push({ title: q.title, meta: `Qualification · ${q.equipment_name || "under review"}`, open: () => openQual(q.id) }));

    (Array.isArray(riskReview) ? riskReview : []).forEach(r =>
      reviewPending.push({ title: r.title, meta: `Risk Assessment · ${r.assessment_type || "in review"}`, open: () => openRisk(r.id) }));

    return { approvalPending, reviewPending, documentPublished };
  }

  function renderGroup(label, dotClass, items) {
    if (!items.length) return "";
    return `
      <div class="hdr-notif-group-label">${esc(label)}</div>
      ${items.slice(0, 6).map((item, i) => `
        <div class="hdr-notif-item" data-group="${esc(label)}" data-idx="${i}">
          <span class="hdr-notif-dot ${dotClass}"></span>
          <div>
            <div class="hdr-notif-item-title">${esc(item.title || "Untitled")}</div>
            <div class="hdr-notif-item-meta">${esc(item.meta || "")}</div>
          </div>
        </div>`).join("")}
    `;
  }

  function render(dropdown, badge, data) {
    const total = data.approvalPending.length + data.reviewPending.length + data.documentPublished.length;

    if (badge) {
      if (total > 0) { badge.style.display = "flex"; badge.textContent = total > 9 ? "9+" : String(total); }
      else badge.style.display = "none";
    }

    if (!total) {
      dropdown.innerHTML = `<div class="hdr-notif-header">Notifications</div>` +
        `<div class="hdr-search-empty">You're all caught up.</div>`;
      return;
    }

    dropdown.innerHTML = `<div class="hdr-notif-header">Notifications</div>` +
      renderGroup("Approval Pending", "hdr-notif-dot-warning", data.approvalPending) +
      renderGroup("Review Pending", "hdr-notif-dot-info", data.reviewPending) +
      renderGroup("Document Published", "hdr-notif-dot-success", data.documentPublished);

    const byGroup = {
      "Approval Pending": data.approvalPending,
      "Review Pending": data.reviewPending,
      "Document Published": data.documentPublished,
    };
    dropdown.querySelectorAll(".hdr-notif-item").forEach(row => {
      row.addEventListener("click", () => {
        const item = byGroup[row.dataset.group][Number(row.dataset.idx)];
        if (item && item.open) item.open();
        closeDropdown(dropdown);
      });
    });
  }

  function closeDropdown(dropdown) {
    dropdown.style.display = "none";
    const btn = document.getElementById("hdr-notif-btn");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  let lastData = { approvalPending: [], reviewPending: [], documentPublished: [] };

  function refresh() {
    if (!window.PharmaAuth || !window.PharmaAuth.isAuthenticated()) return;
    fetchAll().then(data => {
      lastData = data;
      const dropdown = document.getElementById("hdr-notif-dropdown");
      const badge = document.getElementById("hdr-notif-badge");
      if (dropdown && badge) render(dropdown, badge, data);
    });
  }
  window.PharmaNotifications = { refresh };

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("hdr-notif-btn");
    const dropdown = document.getElementById("hdr-notif-dropdown");
    if (!btn || !dropdown) return;

    btn.addEventListener("click", (evt) => {
      evt.stopPropagation();
      const open = dropdown.style.display === "block";
      if (open) {
        closeDropdown(dropdown);
      } else {
        render(dropdown, document.getElementById("hdr-notif-badge"), lastData);
        dropdown.style.display = "block";
        btn.setAttribute("aria-expanded", "true");
      }
    });

    document.addEventListener("click", (evt) => {
      if (!evt.target.closest(".hdr-notif-wrap")) closeDropdown(dropdown);
    });

    refresh();
    setInterval(refresh, 120000); // 2 min — same data every open-suite dashboard already fetches
  });
})();
