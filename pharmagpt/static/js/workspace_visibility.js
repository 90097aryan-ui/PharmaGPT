/**
 * static/js/workspace_visibility.js — Role-based workspace visibility
 * (UI/UX change: role-based workspace visibility).
 *
 * Hides — not just disables — the workspace-selector cards
 * (#view-workspace-selector .ws-card) and the top-level sidebar sections
 * the caller's role doesn't have access to, and auto-enters a user's one
 * accessible workspace instead of making them pick from a one-card
 * selector. Reads `user.accessible_workspaces` (pharmagpt/auth/
 * workspace_access.py, surfaced on both POST /auth/login and GET /auth/me)
 * — the same list the backend enforces per-request via each gated
 * blueprint's before_request hook, so a hidden card is never the only
 * thing standing between an unauthorized user and that workspace's data.
 *
 * Called from static/js/auth.js::showApp(), the same call site that
 * already invokes admin_assume_context.js's applyRoleBasedVisibility() for
 * the Administration section — this file owns workspace-level visibility,
 * that one continues to own admin-level visibility.
 */
(function () {
  "use strict";

  const ADMIN_ROLES = new Set(["company_admin", "super_admin"]);

  // workspace key -> the sidebar nav element whose click already opens that
  // workspace, matching each .ws-card's existing onclick. Reused for
  // single-workspace auto-entry.
  const WORKSPACE_ENTRY_NAV_ID = {
    dashboard: "nav-dashboard",
    validation: "risk-nav-dashboard",
    quality: "nav-qms-dashboard",
    knowledge: "nav-kb",
    documents: "nav-qms-documents",
    pharmapilot: "nav-pharmapilot",
  };

  function applyWorkspaceVisibility(user) {
    const role = user && user.role;
    const isAdmin = ADMIN_ROLES.has(role);
    const accessible = new Set((user && user.accessible_workspaces) || []);

    const gatedEls = document.querySelectorAll("[data-workspace]");
    gatedEls.forEach((el) => {
      const visible = isAdmin || accessible.has(el.dataset.workspace);
      el.style.display = visible ? "" : "none";
    });

    // Yuktav UI Redesign: Document Control's primary sidebar row merges two
    // previously-independent sections (Document Generator + Knowledge Base),
    // each gated by its own single workspace key. A single [data-workspace]
    // check would wrongly hide the whole row for a user who has only one of
    // the two. [data-workspace-any] is visible if the user has ANY of a
    // comma-separated list — additive to the check above, does not change
    // how [data-workspace] itself behaves anywhere else.
    const anyGatedEls = document.querySelectorAll("[data-workspace-any]");
    anyGatedEls.forEach((el) => {
      const keys = el.dataset.workspaceAny.split(",").map((k) => k.trim());
      const visible = isAdmin || keys.some((k) => accessible.has(k));
      el.style.display = visible ? "" : "none";
    });

    const usernameEl = document.getElementById("ws-selector-username");
    if (usernameEl) usernameEl.textContent = (user && (user.display_name || user.email)) || "back";

    if (isAdmin) return; // Company Admin/Super Admin always get the full selector.

    // If exactly one workspace is accessible, skip the selector screen
    // entirely and land the user directly in it — no picking from a
    // one-card grid.
    const accessibleList = Array.from(accessible);
    if (accessibleList.length === 1) {
      const navId = WORKSPACE_ENTRY_NAV_ID[accessibleList[0]];
      const navEl = navId && document.getElementById(navId);
      if (navEl) navEl.click();
    }
  }
  window.applyWorkspaceVisibility = applyWorkspaceVisibility;
})();
