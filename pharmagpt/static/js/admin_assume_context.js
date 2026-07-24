/**
 * static/js/admin_assume_context.js — Assume Company Context UI (Phase 3.5).
 *
 * Talks to routes/auth.py's GET /auth/companies, POST /auth/assume-company,
 * POST /auth/end-assume-company, and reads the assumed-context fields
 * GET /auth/me now includes. The actual company_id override happens
 * entirely server-side (pharmagpt/auth/middleware.py) — this file only
 * drives the picker and renders the persistent banner.
 *
 * Also owns applyRoleBasedVisibility(user), called from auth.js::showApp()
 * on every login/session-restore — the one place role-gated nav visibility
 * (Administration section) is decided, since no such mechanism existed
 * before this phase (every nav item was visible to every role).
 */
(function () {
  "use strict";

  function el(id) { return document.getElementById(id); }

  let countdownTimer = null;

  function applyRoleBasedVisibility(user) {
    const role = user && user.role;
    const adminSection = el("admin-nav-section");
    const companiesNav = el("nav-admin-companies");
    const usersNav = el("nav-admin-users");
    const assumeBtn = el("btn-assume-context");

    const isSuperAdmin = role === "super_admin";
    const isCompanyAdmin = role === "company_admin";
    const hasAssumedContext = !!(user && user.assumed_company_id);

    if (companiesNav) companiesNav.style.display = isSuperAdmin ? "flex" : "none";
    if (usersNav) usersNav.style.display = (isCompanyAdmin || (isSuperAdmin && hasAssumedContext)) ? "flex" : "none";
    if (adminSection) adminSection.style.display = (isSuperAdmin || isCompanyAdmin) ? "block" : "none";
    if (assumeBtn) assumeBtn.style.display = isSuperAdmin ? "inline-flex" : "none";

    renderBanner(user);
  }
  window.applyRoleBasedVisibility = applyRoleBasedVisibility;

  function renderBanner(user) {
    const banner = el("assume-context-banner");
    const text = el("assume-context-banner-text");
    if (!banner || !text) return;

    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }

    if (!user || !user.assumed_company_id) {
      banner.style.display = "none";
      return;
    }

    banner.style.display = "flex";
    const expiresAt = user.break_glass_expires_at ? new Date(user.break_glass_expires_at) : null;

    function update() {
      let suffix = "";
      if (expiresAt) {
        const minsLeft = Math.max(0, Math.round((expiresAt.getTime() - Date.now()) / 60000));
        suffix = minsLeft > 0 ? `, expires in ${minsLeft} min` : ", expiring…";
        if (minsLeft <= 0) {
          // Don't trust the client clock alone — confirm with the server,
          // which is the actual authority (middleware.py re-checks the
          // grant on every request).
          refreshMe();
        }
      }
      text.textContent = `Acting as ${user.assumed_company_name || "a company"} (Super Admin)${suffix}`;
    }
    update();
    countdownTimer = setInterval(update, 30000);
  }

  async function refreshMe() {
    try {
      const res = await window.fetch("/auth/me");
      if (!res.ok) return;
      const user = await res.json();
      if (window.PharmaAuth && window.PharmaAuth.getUser) {
        const stored = window.PharmaAuth.getUser();
        if (stored) Object.assign(stored, user);
      }
      applyRoleBasedVisibility(user);
    } catch (err) {
      // best-effort — the banner just won't update until the next natural refresh
    }
  }

  // ── Picker modal ─────────────────────────────────────────────────────────
  async function openPicker() {
    const select = el("ac-context-company");
    select.innerHTML = "<option>Loading…</option>";
    el("assume-context-modal").classList.add("open");
    el("assume-context-modal-overlay").classList.add("open");

    try {
      const res = await window.fetch("/auth/companies");
      const companies = await res.json();
      if (!res.ok) throw new Error((companies && companies.error) || "Could not load companies");
      select.innerHTML = (companies || [])
        .map(c => `<option value="${c.id}">${c.legal_name} (${c.status})</option>`)
        .join("") || "<option value=''>No companies found</option>";
    } catch (err) {
      select.innerHTML = "<option value=''>Could not load companies</option>";
    }
  }

  function closePicker() {
    el("assume-context-modal").classList.remove("open");
    el("assume-context-modal-overlay").classList.remove("open");
  }

  async function handleAssumeSubmit(evt) {
    evt.preventDefault();
    const company_id = el("ac-context-company").value;
    const reason = el("ac-context-reason").value.trim();
    const duration_minutes = parseInt(el("ac-context-duration").value, 10) || 60;
    if (!company_id || !reason) return;

    const saveBtn = el("assume-context-modal-save");
    saveBtn.disabled = true;
    try {
      const res = await window.fetch("/auth/assume-company", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_id, reason, duration_minutes }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (window.PharmaAuth) window.PharmaAuth.showToast(data.error || "Could not start Assume Company Context.");
        return;
      }
      closePicker();
      el("assume-context-form").reset();
      await refreshMe();
      if (window.loadDashboard) window.loadDashboard();
      if (window.loadProjects) window.loadProjects();
    } finally {
      saveBtn.disabled = false;
    }
  }

  async function handleEndAssume() {
    try {
      await window.fetch("/auth/end-assume-company", { method: "POST" });
    } catch (err) { /* best-effort */ }
    await refreshMe();
    if (window.loadDashboard) window.loadDashboard();
    if (window.loadProjects) window.loadProjects();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const assumeBtn = el("btn-assume-context");
    if (assumeBtn) assumeBtn.addEventListener("click", openPicker);

    const closeBtn = el("assume-context-modal-close");
    if (closeBtn) closeBtn.addEventListener("click", closePicker);
    const cancelBtn = el("assume-context-modal-cancel");
    if (cancelBtn) cancelBtn.addEventListener("click", closePicker);
    const overlay = el("assume-context-modal-overlay");
    if (overlay) overlay.addEventListener("click", closePicker);

    const form = el("assume-context-form");
    if (form) form.addEventListener("submit", handleAssumeSubmit);

    const endBtn = el("btn-end-assume-context");
    if (endBtn) endBtn.addEventListener("click", handleEndAssume);
  });
})();
