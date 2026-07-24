/**
 * static/js/admin_companies.js — Company Administration UI (Phase 3.5).
 * Super Admin only (routes/companies.py enforces this server-side too).
 */
(function () {
  "use strict";

  function el(id) { return document.getElementById(id); }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  async function loadAdminCompanies() {
    const listEl = el("admin-companies-list");
    const emptyEl = el("admin-companies-empty");
    if (!listEl) return;

    try {
      const res = await window.fetch("/companies");
      const companies = await res.json();
      if (!res.ok) throw new Error((companies && companies.error) || "Could not load companies");

      if (!companies.length) {
        listEl.innerHTML = "";
        if (emptyEl) emptyEl.style.display = "flex";
        return;
      }
      if (emptyEl) emptyEl.style.display = "none";

      listEl.innerHTML = companies.map(c => `
        <div class="eq-row" data-company-id="${c.id}" style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border)">
          <div>
            <strong>${escapeHtml(c.legal_name)}</strong>
            <span style="color:var(--text-muted);font-size:12px;margin-left:8px">${escapeHtml(c.industry_segment)} · ${escapeHtml(c.plan_tier)}</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="eq-count" style="background:${c.status === 'active' ? 'var(--success-bg, #E6F4EA)' : 'var(--danger-bg, #FCE8E6)'}">${escapeHtml(c.status)}</span>
            ${c.status === "active"
              ? `<button class="btn-secondary admin-company-suspend" data-id="${c.id}">Suspend</button>`
              : `<button class="btn-secondary admin-company-reactivate" data-id="${c.id}">Reactivate</button>`}
          </div>
        </div>
      `).join("");

      listEl.querySelectorAll(".admin-company-suspend").forEach(btn =>
        btn.addEventListener("click", () => setCompanyStatus(btn.dataset.id, "suspend")));
      listEl.querySelectorAll(".admin-company-reactivate").forEach(btn =>
        btn.addEventListener("click", () => setCompanyStatus(btn.dataset.id, "reactivate")));
    } catch (err) {
      listEl.innerHTML = `<p style="padding:16px;color:var(--text-muted)">Could not load companies.</p>`;
    }
  }
  window.loadAdminCompanies = loadAdminCompanies;

  async function setCompanyStatus(companyId, action) {
    await window.fetch(`/companies/${companyId}/${action}`, { method: "POST" });
    loadAdminCompanies();
  }

  function openModal() {
    el("admin-company-form").reset();
    el("admin-company-modal").classList.add("open");
    el("admin-company-modal-overlay").classList.add("open");
  }

  function closeModal() {
    el("admin-company-modal").classList.remove("open");
    el("admin-company-modal-overlay").classList.remove("open");
  }

  async function handleSubmit(evt) {
    evt.preventDefault();
    const payload = {
      legal_name: el("ac-legal-name").value.trim(),
      industry_segment: el("ac-industry").value,
      admin_email: el("ac-admin-email").value.trim(),
      admin_display_name: el("ac-admin-name").value.trim(),
    };

    const saveBtn = el("admin-company-modal-save");
    saveBtn.disabled = true;
    try {
      const res = await window.fetch("/companies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        if (window.PharmaAuth) window.PharmaAuth.showToast(data.error || "Could not create company.");
        if (!res.ok) return;
      }
      if (data.admin && data.admin.temporary_password) {
        window.alert(
          `Company created. First Company Admin: ${data.admin.email}\n` +
          `Temporary password (relay this out-of-band — shown once): ${data.admin.temporary_password}`
        );
      }
      closeModal();
      loadAdminCompanies();
    } finally {
      saveBtn.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const newBtn = el("btn-new-company");
    if (newBtn) newBtn.addEventListener("click", openModal);
    const closeBtn = el("admin-company-modal-close");
    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    const cancelBtn = el("admin-company-modal-cancel");
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);
    const overlay = el("admin-company-modal-overlay");
    if (overlay) overlay.addEventListener("click", closeModal);
    const form = el("admin-company-form");
    if (form) form.addEventListener("submit", handleSubmit);
  });
})();
