/**
 * workspace.js — Enterprise Workspace shell (reusable across every module)
 *
 * A thin, framework-free helper any module view can call into for consistent
 * workspace chrome: hide/restore the global top header, render a
 * Dashboard > Project > Module > Step breadcrumb, render a step-progress
 * bar, and show a styled Yes/No confirmation dialog (reusing the existing
 * .modal / .btn-primary / .btn-secondary / .btn-danger tokens from
 * style.css instead of a native browser confirm()).
 *
 * Equipment Profile and Project Workspace are the current consumers. Future
 * modules (Risk, URS, Qualification, Validation Report, QMS Change Control/
 * CAPA/Deviation/NCR/OOS-OOT) should wrap their view in `<main class="ent-workspace">`
 * with `.ent-ws-header` / `.ent-ws-toolbar` / `.ent-ws-progress` rows (see
 * workspace.css) and call into this same module rather than duplicating it.
 */
const Workspace = (function () {

  function enter() {
    document.body.classList.add("ent-ws-active");
  }

  function exit() {
    document.body.classList.remove("ent-ws-active");
  }

  // crumbs: [{ label, current }] — `current` marks the final, non-clickable crumb.
  function renderBreadcrumb(target, crumbs) {
    const el = typeof target === "string" ? document.getElementById(target) : target;
    if (!el) return;
    el.innerHTML = crumbs.map((c, i) => {
      const sep = i > 0 ? '<span class="ent-ws-crumb-sep">›</span>' : "";
      const cls = c.current ? "ent-ws-crumb-current" : "";
      return `${sep}<span class="${cls}">${_esc(c.label)}</span>`;
    }).join("");
  }

  // steps: ordered array of step labels; activeIndex: 1-based current step.
  function renderProgress(target, steps, activeIndex) {
    const el = typeof target === "string" ? document.getElementById(target) : target;
    if (!el) return;
    el.innerHTML = steps.map((label, i) => {
      const n     = i + 1;
      const state = n < activeIndex ? "done" : n === activeIndex ? "active" : "";
      const dot   = `<div class="ent-ws-step-dot ${state}">${n < activeIndex ? "<span class=\'icon\' data-lucide=\'check\'></span>" : n}</div>`;
      const lbl   = `<span class="ent-ws-step-label ${state}">${_esc(label)}</span>`;
      const line  = n < steps.length ? `<div class="ent-ws-step-line ${n < activeIndex ? "done" : ""}"></div>` : "";
      return dot + lbl + line;
    }).join("");
  }

  // Returns a Promise<boolean> — resolves true if the user picked confirmLabel.
  function confirmDialog(opts) {
    const {
      title        = "Are you sure?",
      message      = "",
      confirmLabel = "Yes",
      cancelLabel  = "No",
      danger       = false,
    } = opts || {};

    return new Promise((resolve) => {
      let overlay = document.getElementById("ent-ws-confirm-overlay");
      let modal   = document.getElementById("ent-ws-confirm-modal");
      if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "ent-ws-confirm-overlay";
        overlay.className = "modal-overlay";
        modal = document.createElement("div");
        modal.id = "ent-ws-confirm-modal";
        modal.className = "modal";
        document.body.appendChild(overlay);
        document.body.appendChild(modal);
      }

      modal.innerHTML = `
        <div class="modal-header"><h2>${_esc(title)}</h2></div>
        <div class="modal-body"><p style="font-size:13px;color:var(--text);line-height:1.6;padding-bottom:16px;margin:0;">${_esc(message)}</p></div>
        <div class="modal-footer">
          <button class="btn-secondary" id="ent-ws-confirm-no">${_esc(cancelLabel)}</button>
          <button class="${danger ? "btn-danger" : "btn-primary"}" id="ent-ws-confirm-yes">${_esc(confirmLabel)}</button>
        </div>`;

      const close = (result) => {
        overlay.classList.remove("open");
        modal.classList.remove("open");
        overlay.onclick = null;
        resolve(result);
      };

      overlay.classList.add("open");
      modal.classList.add("open");
      document.getElementById("ent-ws-confirm-yes").onclick = () => close(true);
      document.getElementById("ent-ws-confirm-no").onclick  = () => close(false);
      overlay.onclick = () => close(false);
    });
  }

  function _esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  return { enter, exit, renderBreadcrumb, renderProgress, confirmDialog };
})();

window.Workspace = Workspace;
