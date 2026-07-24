/* error_pages.js — Phase 5: full-page 403/404/500/Network/Permission-Denied
 * states. Additive `<main id="view-error-*">` blocks (index.html), shown
 * via the existing generic window.showView() — no new navigation engine.
 *
 * Deliberately NOT wired to every failed fetch — this app's suites already
 * degrade gracefully per-card/per-panel (ui_states.js's errorState, wired
 * across ~20 files in Batches 1 & 6), which is the right UX for one card
 * failing while the rest of a screen works. A full-page takeover is only
 * appropriate when the failure is global, not local to one panel:
 *
 *   - Network Error: real browser connectivity loss (online/offline
 *     events), or a fetch that rejects outright (DNS/connection failure,
 *     as opposed to a non-2xx HTTP response) from qmsFetch's centralized
 *     wrapper (qms_common.js) — a rejected fetch usually means the whole
 *     app is unreachable, not just one record.
 *   - 403/404/500/Permission Denied: exposed via window.PharmaErrorPages
 *     .show(kind, opts) for any future call site that needs a full-page
 *     takeover; this app's current per-card degradation already handles
 *     the common per-record cases, so no existing code path currently
 *     forces these three — see PHASE_5_ENTERPRISE_UX_REPORT.md.
 */

(function () {
  "use strict";

  const VIEW_IDS = {
    403: "view-error-403",
    404: "view-error-404",
    500: "view-error-500",
    network: "view-error-network",
    permission: "view-error-permission",
  };

  let previousViewId = null;

  function currentVisibleViewId() {
    let found = null;
    document.querySelectorAll("main[id^='view-']").forEach(v => {
      if (!found && getComputedStyle(v).display !== "none") found = v.id;
    });
    return found;
  }

  function show(kind, opts) {
    const viewId = VIEW_IDS[kind];
    if (!viewId) return;
    opts = opts || {};

    const current = currentVisibleViewId();
    if (current && !current.startsWith("view-error-")) previousViewId = current;

    const msgEl = document.getElementById(`error-${kind}-message`);
    if (msgEl && opts.message) msgEl.textContent = opts.message;

    const retryBtn = document.getElementById(`error-${kind}-retry`);
    if (retryBtn) {
      const clone = retryBtn.cloneNode(true); // drop any previous handler before rebinding
      retryBtn.parentNode.replaceChild(clone, retryBtn);
      if (typeof opts.onRetry === "function") {
        clone.addEventListener("click", opts.onRetry);
      } else {
        clone.addEventListener("click", () => hide());
      }
    }

    if (window.showView) window.showView(viewId);
  }

  function hide() {
    if (window.showView) window.showView(previousViewId || "view-dashboard");
  }

  window.PharmaErrorPages = { show, hide };

  // ── Real, global triggers only ──────────────────────────────────────────
  window.addEventListener("offline", () => show("network"));
  window.addEventListener("online", () => hide());
})();
