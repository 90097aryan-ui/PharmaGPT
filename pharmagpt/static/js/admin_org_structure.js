/**
 * static/js/admin_org_structure.js — Department & Designation Management UI
 * (RBAC framework, additive). Talks to pharmagpt/routes/org_structure.py.
 * Same visibility/gating as admin_users.js (see admin_assume_context.js::
 * applyRoleBasedVisibility) and the same fetch/toast conventions.
 */
(function () {
  "use strict";

  function el(id) { return document.getElementById(id); }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function toast(msg) {
    if (window.PharmaAuth) window.PharmaAuth.showToast(msg);
  }

  async function loadAdminDepartments() {
    await Promise.all([loadDepartments(), loadDesignations()]);
  }
  window.loadAdminDepartments = loadAdminDepartments;

  async function loadDepartments() {
    const listEl = el("admin-departments-list");
    if (!listEl) return;
    try {
      const res = await window.fetch("/org/departments");
      const rows = await res.json();
      if (!res.ok) throw new Error((rows && rows.error) || "Could not load departments");

      listEl.innerHTML = (rows || []).map(d => `
        <div class="eq-row" data-id="${d.id}" style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid var(--border)">
          <div><strong>${escapeHtml(d.name)}</strong>
            <span style="color:var(--text-muted);font-size:12px;margin-left:8px">${escapeHtml(d.department_code)} &middot; ${escapeHtml(d.status)}</span>
          </div>
          <button class="btn-secondary dept-toggle-status" data-id="${d.id}" data-status="${d.status}">
            ${d.status === "active" ? "Disable" : "Enable"}
          </button>
        </div>
      `).join("") || `<p style="padding:16px;color:var(--text-muted)">No departments yet.</p>`;

      listEl.querySelectorAll(".dept-toggle-status").forEach(btn =>
        btn.addEventListener("click", () => toggleDepartmentStatus(btn.dataset.id, btn.dataset.status)));
    } catch (err) {
      listEl.innerHTML = `<p style="padding:16px;color:var(--text-muted)">Could not load departments.</p>`;
    }
  }

  async function toggleDepartmentStatus(id, currentStatus) {
    const reason = window.prompt("Reason for this change (required):");
    if (!reason) return;
    const res = await window.fetch(`/org/departments/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: currentStatus === "active" ? "disabled" : "active", reason }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      toast(data.error || "Could not update department.");
    }
    loadDepartments();
  }

  async function loadDesignations() {
    const listEl = el("admin-designations-list");
    if (!listEl) return;
    try {
      const res = await window.fetch("/org/designations");
      const rows = await res.json();
      if (!res.ok) throw new Error((rows && rows.error) || "Could not load designations");

      listEl.innerHTML = (rows || []).map(d => `
        <div class="eq-row" data-id="${d.id}" style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid var(--border)">
          <strong>${escapeHtml(d.name)}</strong>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="color:var(--text-muted);font-size:12px">${escapeHtml(d.status)}</span>
            <button class="btn-secondary desig-toggle-status" data-id="${d.id}" data-status="${d.status}">
              ${d.status === "active" ? "Disable" : "Enable"}
            </button>
          </div>
        </div>
      `).join("") || `<p style="padding:16px;color:var(--text-muted)">No designations yet.</p>`;

      listEl.querySelectorAll(".desig-toggle-status").forEach(btn =>
        btn.addEventListener("click", () => toggleDesignationStatus(btn.dataset.id, btn.dataset.status)));
    } catch (err) {
      listEl.innerHTML = `<p style="padding:16px;color:var(--text-muted)">Could not load designations.</p>`;
    }
  }

  async function toggleDesignationStatus(id, currentStatus) {
    const reason = window.prompt("Reason for this change (required):");
    if (!reason) return;
    const res = await window.fetch(`/org/designations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: currentStatus === "active" ? "disabled" : "active", reason }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      toast(data.error || "Could not update designation.");
    }
    loadDesignations();
  }

  function openModal(id) { el(id).classList.add("open"); el(`${id}-overlay`).classList.add("open"); }
  function closeModal(id) { el(id).classList.remove("open"); el(`${id}-overlay`).classList.remove("open"); }

  async function handleDepartmentSubmit(evt) {
    evt.preventDefault();
    const payload = {
      name: el("ad-name").value.trim(),
      department_code: el("ad-code").value.trim(),
      reason: el("ad-reason").value.trim(),
    };
    const res = await window.fetch("/org/departments", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.error || "Could not create department."); return; }
    el("admin-department-form").reset();
    closeModal("admin-department-modal");
    loadDepartments();
  }

  async function handleDesignationSubmit(evt) {
    evt.preventDefault();
    const payload = { name: el("ades-name").value.trim(), reason: el("ades-reason").value.trim() };
    const res = await window.fetch("/org/designations", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.error || "Could not create designation."); return; }
    el("admin-designation-form").reset();
    closeModal("admin-designation-modal");
    loadDesignations();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const newDeptBtn = el("btn-new-department");
    if (newDeptBtn) newDeptBtn.addEventListener("click", () => { el("admin-department-form").reset(); openModal("admin-department-modal"); });
    const deptCancel = el("admin-department-modal-cancel");
    if (deptCancel) deptCancel.addEventListener("click", () => closeModal("admin-department-modal"));
    const deptClose = el("admin-department-modal-close");
    if (deptClose) deptClose.addEventListener("click", () => closeModal("admin-department-modal"));
    const deptOverlay = el("admin-department-modal-overlay");
    if (deptOverlay) deptOverlay.addEventListener("click", () => closeModal("admin-department-modal"));
    const deptForm = el("admin-department-form");
    if (deptForm) deptForm.addEventListener("submit", handleDepartmentSubmit);

    const newDesigBtn = el("btn-new-designation");
    if (newDesigBtn) newDesigBtn.addEventListener("click", () => { el("admin-designation-form").reset(); openModal("admin-designation-modal"); });
    const desigCancel = el("admin-designation-modal-cancel");
    if (desigCancel) desigCancel.addEventListener("click", () => closeModal("admin-designation-modal"));
    const desigClose = el("admin-designation-modal-close");
    if (desigClose) desigClose.addEventListener("click", () => closeModal("admin-designation-modal"));
    const desigOverlay = el("admin-designation-modal-overlay");
    if (desigOverlay) desigOverlay.addEventListener("click", () => closeModal("admin-designation-modal"));
    const desigForm = el("admin-designation-form");
    if (desigForm) desigForm.addEventListener("submit", handleDesignationSubmit);
  });
})();
