/* header.js — Phase 5: Global Header (Workspace / Company / Project chips).
 *
 * Purely reads existing state — window.activeProject (projects.js),
 * window.PharmaAuth.getUser() (auth.js), and the assumed-company fields
 * already present on the /auth/me user object (admin_assume_context.js) —
 * and renders it into the new chip elements added in index.html's <header>.
 * Does not touch #user-badge/#btn-assume-context/#btn-logout/
 * #btn-switch-workspace: those keep their existing markup and listeners
 * exactly as-is.
 *
 * "Current Company" honesty note: TenantContext (pharmagpt/auth/context.py)
 * only carries company_id (a UUID), never a name, for any role except a
 * Super Admin with an active Assume-Context grant (which already gets
 * assumed_company_name from /auth/me). Resolving a name for anyone else
 * would require calling GET /auth/companies or GET /companies, both
 * @require_role("super_admin") — out of reach for a company_admin/user.
 * Rather than fabricate a name, the Company chip shows a role label in
 * that case. Search/Notifications dropdown behavior is wired by
 * search.js/notifications.js (Batch 4); this file only owns the chips and
 * the two dropdown mount points' open/close shell.
 */

(function () {
  "use strict";

  const ROLE_LABELS = {
    super_admin: "Super Admin",
    company_admin: "Company Admin",
    user: "User",
  };

  function roleLabel(role) {
    if (!role) return "—";
    return ROLE_LABELS[role] || role.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  // View id -> workspace label, matching the six Phase 4 workspace groups.
  const WORKSPACE_FOR_VIEW = {
    "view-dashboard": "Executive Workspace",

    "view-project-workspace": "Validation Workspace",
    "view-equipment-library": "Validation Workspace",
    "view-equipment-profile": "Validation Workspace",
    "view-validation": "Validation Workspace",
    "view-urs-dashboard": "Validation Workspace",
    "view-urs-list": "Validation Workspace",
    "view-urs-new": "Validation Workspace",
    "view-urs-detail": "Validation Workspace",
    "view-risk-dashboard": "Validation Workspace",
    "view-risk-new": "Validation Workspace",
    "view-risk-library": "Validation Workspace",
    "view-risk-templates": "Validation Workspace",
    "view-risk-reports": "Validation Workspace",
    "view-risk-approval": "Validation Workspace",
    "view-risk-assistant": "Validation Workspace",
    "view-qual": "Validation Workspace",
    "view-report": "Validation Workspace",

    "view-qms-dashboard": "Quality Workspace",
    "view-qms-deviations": "Quality Workspace",
    "view-qms-capa": "Quality Workspace",
    "view-qms-change-control": "Quality Workspace",

    "view-kb": "Knowledge Workspace",

    "view-qms-documents": "Document Workspace",

    "view-pharmapilot": "PharmaPilot",
    "view-chat": "PharmaPilot",

    "view-admin-companies": "Administration",
    "view-admin-users": "Administration",
  };

  // Views with no meaningful workspace/project chip (selector + auth screens).
  const HIDE_CHIPS_FOR_VIEW = new Set(["view-workspace-selector"]);

  function setChip(id, text) {
    const chip = document.getElementById(id);
    if (!chip) return;
    if (!text) {
      chip.style.display = "none";
      return;
    }
    const textEl = chip.querySelector(".hdr-chip-text");
    if (textEl) textEl.textContent = text;
    chip.style.display = "inline-flex";
  }

  function currentVisibleViewId() {
    let found = null;
    document.querySelectorAll("main[id^='view-']").forEach(v => {
      if (!found && getComputedStyle(v).display !== "none") found = v.id;
    });
    return found;
  }

  function renderWorkspaceAndProjectChips() {
    const viewId = currentVisibleViewId();
    if (!viewId || HIDE_CHIPS_FOR_VIEW.has(viewId)) {
      setChip("hdr-chip-workspace", null);
      setChip("hdr-chip-project", null);
      return;
    }
    setChip("hdr-chip-workspace", WORKSPACE_FOR_VIEW[viewId] || null);

    const proj = window.activeProject;
    setChip("hdr-chip-project", proj && proj.name ? proj.name : null);
  }

  function renderUserChips() {
    if (!window.PharmaAuth || !window.PharmaAuth.isAuthenticated()) {
      setChip("hdr-chip-company", null);
      return;
    }
    const user = window.PharmaAuth.getUser();
    if (!user) { setChip("hdr-chip-company", null); return; }

    if (user.assumed_company_id && user.assumed_company_name) {
      setChip("hdr-chip-company", user.assumed_company_name);
    } else {
      setChip("hdr-chip-company", roleLabel(user.role));
    }
  }

  function renderAll() {
    renderWorkspaceAndProjectChips();
    renderUserChips();
  }
  window.PharmaHeader = { render: renderAll };

  // Re-render chips whenever a view's visibility changes — covers every
  // navigation path (sidebar clicks, showView, showAllRiskViews, project
  // selection, "Back to Project", etc.) without coupling to any of them.
  function observeViewChanges() {
    const target = document.querySelector(".app-body") || document.body;
    const observer = new MutationObserver(muts => {
      const relevant = muts.some(m => m.type === "attributes" && m.target.id && m.target.id.startsWith("view-"));
      if (relevant) renderWorkspaceAndProjectChips();
    });
    document.querySelectorAll("main[id^='view-']").forEach(v => {
      observer.observe(v, { attributes: true, attributeFilter: ["style"] });
    });
  }

  // Company/User chip depends on login + Assume-Context state, which
  // changes far less often than navigation — a light poll is enough and
  // avoids coupling to admin_assume_context.js's internals.
  function pollUserState() {
    setInterval(renderUserChips, 4000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    observeViewChanges();
    pollUserState();
    renderAll();

    const projectChip = document.getElementById("hdr-chip-project");
    if (projectChip) {
      projectChip.addEventListener("click", () => {
        if (window.activeProject && window.selectProject) window.selectProject(window.activeProject);
      });
    }
  });

  // Also render right after login/session-restore, when #user-badge first
  // becomes visible (auth.js flips header display:flex at that point).
  const headerVisibilityObserver = new MutationObserver(() => renderAll());
  document.addEventListener("DOMContentLoaded", () => {
    const header = document.querySelector("header");
    if (header) headerVisibilityObserver.observe(header, { attributes: true, attributeFilter: ["style"] });
  });
})();
