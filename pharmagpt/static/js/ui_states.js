/* ui_states.js — Phase 5: shared loading / empty / error state renderers.
   Used by dashboard.js, qms_common.js, and per-suite list/detail modules
   in place of the ad hoc "Loading…" / "-empty" strings each used to
   hand-roll. Pure rendering helpers — no fetch/business logic here. */

window.PharmaUI = (function () {

  function resolveEl(target) {
    return typeof target === "string" ? document.getElementById(target) : target;
  }

  function uid(prefix) {
    return prefix + "-" + Math.random().toString(36).slice(2, 9);
  }

  function iconSpan(name, extraClass) {
    return `<span class="icon${extraClass ? " " + extraClass : ""}" data-lucide="${name}"></span>`;
  }

  // ── Loading (skeleton) ───────────────────────────────────────────────────
  // variant: "rows" (default — list/card rows), "table" (header+rows), "text" (a few lines)
  function skeleton(target, opts) {
    const el = resolveEl(target);
    if (!el) return;
    opts = opts || {};
    const rows = opts.rows || 3;
    const variant = opts.variant || "rows";

    if (variant === "table") {
      let cols = opts.cols || 4;
      let head = "";
      for (let c = 0; c < cols; c++) head += '<div class="ui-skeleton-cell"></div>';
      let body = "";
      for (let r = 0; r < rows; r++) {
        let cells = "";
        for (let c = 0; c < cols; c++) cells += '<div class="ui-skeleton-cell"></div>';
        body += `<div class="ui-skeleton-table-row">${cells}</div>`;
      }
      el.innerHTML = `<div class="ui-skeleton ui-skeleton-table">
        <div class="ui-skeleton-table-row ui-skeleton-table-head">${head}</div>${body}</div>`;
      return;
    }

    if (variant === "text") {
      let lines = "";
      for (let i = 0; i < rows; i++) {
        lines += `<div class="ui-skeleton-line" style="width:${i === rows - 1 ? "60%" : "100%"}"></div>`;
      }
      el.innerHTML = `<div class="ui-skeleton ui-skeleton-text">${lines}</div>`;
      return;
    }

    // default: "rows"
    let rowsHtml = "";
    for (let i = 0; i < rows; i++) {
      rowsHtml += `<div class="ui-skeleton-row">
        <div class="ui-skeleton-avatar"></div>
        <div class="ui-skeleton-row-lines">
          <div class="ui-skeleton-line" style="width:70%"></div>
          <div class="ui-skeleton-line ui-skeleton-line-sm" style="width:40%"></div>
        </div>
      </div>`;
    }
    el.innerHTML = `<div class="ui-skeleton ui-skeleton-rows">${rowsHtml}</div>`;
  }

  // ── Empty state ──────────────────────────────────────────────────────────
  // opts: { icon, title, message, actionLabel, onAction }
  function emptyState(target, opts) {
    const el = resolveEl(target);
    if (!el) return;
    opts = opts || {};
    const icon = opts.icon || "inbox";
    const title = opts.title || "Nothing here yet";
    const message = opts.message || "";

    let actionHtml = "";
    let actionId = "";
    if (opts.actionLabel && typeof opts.onAction === "function") {
      actionId = uid("ui-empty-action");
      actionHtml = `<button type="button" class="ui-state-action" id="${actionId}">${opts.actionLabel}</button>`;
    }

    el.innerHTML = `
      <div class="ui-empty-state">
        <div class="ui-state-icon">${iconSpan(icon)}</div>
        <div class="ui-state-title">${title}</div>
        ${message ? `<div class="ui-state-message">${message}</div>` : ""}
        ${actionHtml}
      </div>`;

    if (window.refreshIcons) window.refreshIcons();
    if (actionId) {
      const btn = document.getElementById(actionId);
      if (btn) btn.addEventListener("click", opts.onAction);
    }
  }

  // ── Error state ──────────────────────────────────────────────────────────
  // opts: { message, onRetry }
  function errorState(target, opts) {
    const el = resolveEl(target);
    if (!el) return;
    opts = opts || {};
    const message = opts.message || "Something went wrong while loading this.";

    let retryHtml = "";
    let retryId = "";
    if (typeof opts.onRetry === "function") {
      retryId = uid("ui-error-retry");
      retryHtml = `<button type="button" class="ui-state-action ui-state-action-retry" id="${retryId}">Try again</button>`;
    }

    el.innerHTML = `
      <div class="ui-error-state">
        <div class="ui-state-icon ui-state-icon-error">${iconSpan("alert-triangle")}</div>
        <div class="ui-state-title">Unable to load</div>
        <div class="ui-state-message">${message}</div>
        ${retryHtml}
      </div>`;

    if (window.refreshIcons) window.refreshIcons();
    if (retryId) {
      const btn = document.getElementById(retryId);
      if (btn) btn.addEventListener("click", opts.onRetry);
    }
  }

  return { skeleton, emptyState, errorState };
})();
