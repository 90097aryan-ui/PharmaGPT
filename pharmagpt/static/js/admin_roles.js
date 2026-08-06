/**
 * static/js/admin_roles.js — Role & Permission Management UI (RBAC
 * framework, additive). Talks to pharmagpt/routes/rbac.py. Same
 * visibility/gating and fetch/toast conventions as admin_users.js.
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

  let _roles = [];
  let _users = [];

  async function loadAdminRoles() {
    await loadRoles();
    await loadUsersForAssignment();
  }
  window.loadAdminRoles = loadAdminRoles;

  async function loadRoles() {
    const listEl = el("admin-roles-list");
    if (!listEl) return;
    try {
      const res = await window.fetch("/rbac/roles");
      const rows = await res.json();
      if (!res.ok) throw new Error((rows && rows.error) || "Could not load roles");
      _roles = rows || [];

      listEl.innerHTML = _roles.map(r => `
        <div class="eq-row" data-id="${r.id}" style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid var(--border)">
          <div>
            <strong>${escapeHtml(r.name)}</strong>
            ${r.is_template ? `<span style="color:var(--text-muted);font-size:11px;margin-left:8px">TEMPLATE</span>` : ""}
            <div style="color:var(--text-muted);font-size:12px">${escapeHtml(r.description || "")}</div>
          </div>
          <div style="display:flex;gap:8px">
            ${r.is_template
              ? `<button class="btn-secondary role-clone-btn" data-id="${r.id}" data-name="${escapeHtml(r.name)}">Clone</button>`
              : `<span style="color:var(--text-muted);font-size:12px">${escapeHtml(r.status)}</span>
                 <button class="btn-secondary role-toggle-status" data-id="${r.id}" data-status="${r.status}">
                   ${r.status === "active" ? "Disable" : "Enable"}
                 </button>`}
          </div>
        </div>
      `).join("") || `<p style="padding:16px;color:var(--text-muted)">No roles yet.</p>`;

      listEl.querySelectorAll(".role-toggle-status").forEach(btn =>
        btn.addEventListener("click", () => toggleRoleStatus(btn.dataset.id, btn.dataset.status)));
      listEl.querySelectorAll(".role-clone-btn").forEach(btn =>
        btn.addEventListener("click", () => cloneRole(btn.dataset.id, btn.dataset.name)));

      populateMatrixRoleSelect();
    } catch (err) {
      listEl.innerHTML = `<p style="padding:16px;color:var(--text-muted)">Could not load roles.</p>`;
    }
  }

  async function toggleRoleStatus(id, currentStatus) {
    const reason = window.prompt("Reason for this change (required):");
    if (!reason) return;
    const res = await window.fetch(`/rbac/roles/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: currentStatus === "active" ? "disabled" : "active", reason }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      toast(data.error || "Could not update role.");
    }
    loadRoles();
  }

  async function cloneRole(sourceId, sourceName) {
    const name = window.prompt("Name for the cloned role:", `${sourceName} (Company)`);
    if (!name) return;
    const reason = window.prompt("Reason for this change (required):");
    if (!reason) return;
    const res = await window.fetch(`/rbac/roles/${sourceId}/clone`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, reason }),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.error || "Could not clone role."); return; }
    loadRoles();
  }

  // ── Permission Matrix tab ────────────────────────────────────────────────

  function populateMatrixRoleSelect() {
    const sel = el("rbac-matrix-role-select");
    if (!sel) return;
    const nonTemplateRoles = _roles.filter(r => !r.is_template);
    sel.innerHTML = nonTemplateRoles.map(r => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join("");
    if (nonTemplateRoles.length) loadMatrixForRole(nonTemplateRoles[0].id);
  }

  async function loadMatrixForRole(roleId) {
    const gridEl = el("rbac-matrix-grid");
    if (!gridEl || !roleId) return;
    try {
      const res = await window.fetch(`/rbac/roles/${roleId}/permissions`);
      const rows = await res.json();
      if (!res.ok) throw new Error((rows && rows.error) || "Could not load permission matrix");

      const modules = [...new Set(rows.map(r => r.module))];
      const actions = [...new Set(rows.map(r => r.action))];
      const cellByKey = {};
      rows.forEach(r => { cellByKey[`${r.module}::${r.action}`] = r; });

      let html = `<table style="border-collapse:collapse;width:100%"><thead><tr><th style="text-align:left;padding:6px">Module</th>`;
      actions.forEach(a => { html += `<th style="padding:6px;font-size:12px">${escapeHtml(a)}</th>`; });
      html += `</tr></thead><tbody>`;
      modules.forEach(m => {
        html += `<tr><td style="padding:6px;font-weight:600">${escapeHtml(m)}</td>`;
        actions.forEach(a => {
          const cell = cellByKey[`${m}::${a}`];
          html += `<td style="padding:6px;text-align:center">
            <input type="checkbox" class="rbac-matrix-cell" data-permission-id="${cell.permission_id}"
                   data-module="${escapeHtml(m)}" data-action="${escapeHtml(a)}" ${cell.granted ? "checked" : ""} />
          </td>`;
        });
        html += `</tr>`;
      });
      html += `</tbody></table>`;
      gridEl.innerHTML = html;

      gridEl.querySelectorAll(".rbac-matrix-cell").forEach(cb =>
        cb.addEventListener("change", () => toggleMatrixCell(roleId, cb)));
    } catch (err) {
      gridEl.innerHTML = `<p style="padding:16px;color:var(--text-muted)">Could not load the permission matrix.</p>`;
    }
  }

  async function toggleMatrixCell(roleId, checkbox) {
    const reason = window.prompt(`Reason for changing '${checkbox.dataset.action}' on '${checkbox.dataset.module}' (required):`);
    if (!reason) { checkbox.checked = !checkbox.checked; return; }
    const res = await window.fetch(`/rbac/roles/${roleId}/permissions`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ permission_id: checkbox.dataset.permissionId, granted: checkbox.checked, reason }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      toast(data.error || "Could not update permission.");
      checkbox.checked = !checkbox.checked;
    }
  }

  // ── User Assignment tab ──────────────────────────────────────────────────

  async function loadUsersForAssignment() {
    const sel = el("rbac-assign-user-select");
    if (!sel) return;
    try {
      const res = await window.fetch("/users/directory");
      const rows = await res.json();
      if (!res.ok) throw new Error((rows && rows.error) || "Could not load users");
      _users = rows || [];
      sel.innerHTML = _users.map(u => `<option value="${u.user_id}">${escapeHtml(u.display_name)}</option>`).join("");
      if (_users.length) loadUserAssignment(_users[0].user_id);
    } catch (err) {
      sel.innerHTML = "";
    }
  }

  async function loadUserAssignment(userId) {
    const listEl = el("rbac-assign-roles-list");
    const effEl = el("rbac-assign-effective");
    if (!listEl || !userId) return;

    const [rolesRes, effRes] = await Promise.all([
      window.fetch(`/rbac/users/${userId}/roles`),
      window.fetch(`/rbac/users/${userId}/effective-permissions`),
    ]);
    const assigned = await rolesRes.json().catch(() => []);
    const effective = await effRes.json().catch(() => []);
    const assignedRoleIds = new Set((assigned || []).map(a => a.role_id));

    const assignableRoles = _roles.filter(r => !r.is_template);
    listEl.innerHTML = assignableRoles.map(r => `
      <label style="display:flex;align-items:center;gap:8px;padding:6px 0">
        <input type="checkbox" class="rbac-assign-cb" data-role-id="${r.id}" ${assignedRoleIds.has(r.id) ? "checked" : ""} />
        ${escapeHtml(r.name)}
      </label>
    `).join("") || `<p style="color:var(--text-muted)">No assignable roles yet.</p>`;

    listEl.querySelectorAll(".rbac-assign-cb").forEach(cb =>
      cb.addEventListener("change", () => toggleUserRole(userId, cb)));

    effEl.innerHTML = `<strong>Effective permissions:</strong> ` + (
      (effective || []).length
        ? (effective || []).map(p => `${escapeHtml(p.module)}/${escapeHtml(p.action)}`).join(", ")
        : `<span style="color:var(--text-muted)">none</span>`
    );
  }

  async function toggleUserRole(userId, checkbox) {
    const roleId = checkbox.dataset.roleId;
    const reason = window.prompt("Reason for this change (required):");
    if (!reason) { checkbox.checked = !checkbox.checked; return; }

    let res;
    if (checkbox.checked) {
      res = await window.fetch(`/rbac/users/${userId}/roles`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role_id: roleId, reason }),
      });
    } else {
      res = await window.fetch(`/rbac/users/${userId}/roles/${roleId}`, {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      });
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      toast(data.error || "Could not update role assignment.");
      checkbox.checked = !checkbox.checked;
    }
    loadUserAssignment(userId);
  }

  // ── Audit Trail tab ──────────────────────────────────────────────────────

  async function loadAuditLog() {
    const listEl = el("rbac-audit-list");
    if (!listEl) return;
    try {
      const res = await window.fetch("/rbac/audit");
      const rows = await res.json();
      if (!res.ok) throw new Error((rows && rows.error) || "Could not load audit trail");

      listEl.innerHTML = `<table style="border-collapse:collapse;width:100%;font-size:13px">
        <thead><tr>
          <th style="text-align:left;padding:6px">When</th>
          <th style="text-align:left;padding:6px">Actor</th>
          <th style="text-align:left;padding:6px">Reason</th>
        </tr></thead><tbody>
          ${(rows || []).map(r => `
            <tr style="border-top:1px solid var(--border)">
              <td style="padding:6px">${escapeHtml(r.created_at)}</td>
              <td style="padding:6px">${escapeHtml(r.actor_user_id)}</td>
              <td style="padding:6px">${escapeHtml(r.reason)}</td>
            </tr>`).join("")}
        </tbody></table>` || `<p style="color:var(--text-muted)">No audit entries yet.</p>`;
    } catch (err) {
      listEl.innerHTML = `<p style="padding:16px;color:var(--text-muted)">Could not load the audit trail.</p>`;
    }
  }

  // ── Tabs + New Role modal ────────────────────────────────────────────────

  function switchTab(tab) {
    document.querySelectorAll(".rbac-tab-btn").forEach(b => b.classList.toggle("active", b.dataset.rbacTab === tab));
    document.querySelectorAll(".rbac-tab-panel").forEach(p => {
      p.style.display = p.id === `rbac-tab-${tab}` ? "block" : "none";
    });
    if (tab === "audit") loadAuditLog();
  }

  function openRoleModal() {
    el("admin-role-form").reset();
    el("admin-role-modal").classList.add("open");
    el("admin-role-modal-overlay").classList.add("open");
  }
  function closeRoleModal() {
    el("admin-role-modal").classList.remove("open");
    el("admin-role-modal-overlay").classList.remove("open");
  }

  async function handleRoleSubmit(evt) {
    evt.preventDefault();
    const payload = {
      name: el("ar-name").value.trim(),
      description: el("ar-description").value.trim(),
      reason: el("ar-reason").value.trim(),
    };
    const res = await window.fetch("/rbac/roles", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.error || "Could not create role."); return; }
    closeRoleModal();
    loadRoles();
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".rbac-tab-btn").forEach(btn =>
      btn.addEventListener("click", () => switchTab(btn.dataset.rbacTab)));

    const matrixSel = el("rbac-matrix-role-select");
    if (matrixSel) matrixSel.addEventListener("change", () => loadMatrixForRole(matrixSel.value));

    const assignSel = el("rbac-assign-user-select");
    if (assignSel) assignSel.addEventListener("change", () => loadUserAssignment(assignSel.value));

    const newRoleBtn = el("btn-new-role");
    if (newRoleBtn) newRoleBtn.addEventListener("click", openRoleModal);
    const roleCancel = el("admin-role-modal-cancel");
    if (roleCancel) roleCancel.addEventListener("click", closeRoleModal);
    const roleClose = el("admin-role-modal-close");
    if (roleClose) roleClose.addEventListener("click", closeRoleModal);
    const roleOverlay = el("admin-role-modal-overlay");
    if (roleOverlay) roleOverlay.addEventListener("click", closeRoleModal);
    const roleForm = el("admin-role-form");
    if (roleForm) roleForm.addEventListener("submit", handleRoleSubmit);
  });
})();
