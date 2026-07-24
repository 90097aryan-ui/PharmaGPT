/**
 * static/js/admin_users.js — User Management + Role Management UI (Phase 3.5).
 * Company Admin manages their own company's users. Super Admin only reaches
 * this view (nav visibility, admin_assume_context.js::applyRoleBasedVisibility)
 * while an Assume Company Context session is active — routes/users.py
 * enforces this server-side too.
 */
(function () {
  "use strict";

  function el(id) { return document.getElementById(id); }

  const ROLE_NAMES = { 1: "Super Admin", 2: "Company Admin", 3: "Reviewer / QA", 4: "User" };

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  async function loadAdminUsers() {
    const listEl = el("admin-users-list");
    const emptyEl = el("admin-users-empty");
    const subEl = el("admin-users-sub");
    if (!listEl) return;

    const user = window.PharmaAuth && window.PharmaAuth.getUser();
    if (subEl) {
      subEl.textContent = user && user.role === "super_admin" && user.assumed_company_name
        ? `Users in ${user.assumed_company_name} (assumed context)`
        : "Users in your company";
    }

    try {
      const res = await window.fetch("/users");
      const users = await res.json();
      if (!res.ok) throw new Error((users && users.error) || "Could not load users");

      if (!users.length) {
        listEl.innerHTML = "";
        if (emptyEl) emptyEl.style.display = "flex";
        return;
      }
      if (emptyEl) emptyEl.style.display = "none";

      listEl.innerHTML = users.map(u => `
        <div class="eq-row" data-user-id="${u.id}" style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border)">
          <div>
            <strong>${escapeHtml(u.display_name)}</strong>
            <span style="color:var(--text-muted);font-size:12px;margin-left:8px">${escapeHtml(u.status)}</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <select class="admin-user-role-select" data-id="${u.id}">
              ${[2, 3, 4].map(rid => `<option value="${rid}" ${u.role_id === rid ? "selected" : ""}>${ROLE_NAMES[rid]}</option>`).join("")}
            </select>
            <button class="btn-secondary admin-user-toggle-status" data-id="${u.id}" data-status="${u.status}">
              ${u.status === "active" ? "Deactivate" : "Reactivate"}
            </button>
          </div>
        </div>
      `).join("");

      listEl.querySelectorAll(".admin-user-role-select").forEach(sel =>
        sel.addEventListener("change", () => updateUser(sel.dataset.id, { role_id: parseInt(sel.value, 10) })));
      listEl.querySelectorAll(".admin-user-toggle-status").forEach(btn =>
        btn.addEventListener("click", () => updateUser(btn.dataset.id, {
          status: btn.dataset.status === "active" ? "deactivated" : "active",
        })));
    } catch (err) {
      listEl.innerHTML = `<p style="padding:16px;color:var(--text-muted)">Could not load users.</p>`;
    }
  }
  window.loadAdminUsers = loadAdminUsers;

  async function updateUser(userId, updates) {
    const res = await window.fetch(`/users/${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      if (window.PharmaAuth) window.PharmaAuth.showToast(data.error || "Could not update user.");
    }
    loadAdminUsers();
  }

  function openModal() {
    el("admin-user-form").reset();
    el("admin-user-modal").classList.add("open");
    el("admin-user-modal-overlay").classList.add("open");
  }

  function closeModal() {
    el("admin-user-modal").classList.remove("open");
    el("admin-user-modal-overlay").classList.remove("open");
  }

  async function handleSubmit(evt) {
    evt.preventDefault();
    const payload = {
      email: el("au-email").value.trim(),
      display_name: el("au-display-name").value.trim(),
      role_id: parseInt(el("au-role").value, 10),
    };

    const saveBtn = el("admin-user-modal-save");
    saveBtn.disabled = true;
    try {
      const res = await window.fetch("/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        if (window.PharmaAuth) window.PharmaAuth.showToast(data.error || "Could not invite user.");
        return;
      }
      if (data.temporary_password) {
        window.alert(
          `User invited: ${data.email}\n` +
          `Temporary password (relay this out-of-band — shown once): ${data.temporary_password}`
        );
      }
      closeModal();
      loadAdminUsers();
    } finally {
      saveBtn.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const inviteBtn = el("btn-invite-user");
    if (inviteBtn) inviteBtn.addEventListener("click", openModal);
    const closeBtn = el("admin-user-modal-close");
    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    const cancelBtn = el("admin-user-modal-cancel");
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);
    const overlay = el("admin-user-modal-overlay");
    if (overlay) overlay.addEventListener("click", closeModal);
    const form = el("admin-user-form");
    if (form) form.addEventListener("submit", handleSubmit);
  });
})();
