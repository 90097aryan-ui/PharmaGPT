/**
 * static/js/esignature_dialog.js — the ONE reusable Electronic Signature
 * dialog (21 CFR Part 11 / EU GMP Annex 11), usable from any module's page.
 *
 * Usage: window.PharmaESign.open({
 *   meaning: "Approved",          // pre-selected, still user-editable
 *   onConfirm: async ({password, meaning, reason}) => { ... POST to the
 *     module's own approval/decide endpoint, including these three fields
 *     alongside whatever else that endpoint already expects ... },
 * });
 *
 * Does not itself call any backend route — the caller's onConfirm decides
 * where {password, meaning, reason} get sent, so this one dialog is reusable
 * by every module (Document Control, Deviation, CAPA, Change Control,
 * Validation, IQ/OQ/PQ, Risk Assessment, Training, and any future module)
 * without this file needing to know about any of their endpoints.
 */
(function () {
  "use strict";

  const MEANINGS = ["Created", "Reviewed", "Verified", "Approved", "Authorized", "Released", "Rejected", "Cancelled"];

  function el(id) { return document.getElementById(id); }

  function ensureMarkup() {
    if (el("esign-modal-overlay")) return;
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.id = "esign-modal-overlay";
    const modal = document.createElement("div");
    modal.className = "modal";
    modal.id = "esign-modal";
    modal.innerHTML = `
      <div class="modal-header">
        <h3>Electronic Signature</h3>
        <button class="modal-close" id="esign-modal-close">&times;</button>
      </div>
      <form id="esign-form">
        <div class="form-group">
          <div style="font-size:13px;color:var(--text-muted);line-height:1.6">
            <div><strong>User:</strong> <span id="esign-user-name"></span></div>
            <div><strong>Role:</strong> <span id="esign-user-role"></span></div>
            <div><strong>Department:</strong> <span id="esign-user-department"></span></div>
            <div><strong>Date &amp; Time:</strong> <span id="esign-datetime"></span></div>
          </div>
        </div>
        <div class="form-group">
          <label for="esign-meaning">Signature Meaning *</label>
          <select id="esign-meaning" required>
            ${MEANINGS.map(m => `<option value="${m}">${m}</option>`).join("")}
          </select>
        </div>
        <div class="form-group">
          <label for="esign-reason">Reason for Signature *</label>
          <textarea id="esign-reason" required rows="2" placeholder="Why are you signing this?"></textarea>
        </div>
        <div class="form-group">
          <label for="esign-password">Password (re-authentication) *</label>
          <input type="password" id="esign-password" required autocomplete="current-password" />
        </div>
        <p id="esign-error" style="color:var(--danger,#c0392b);font-size:13px;display:none"></p>
        <div class="modal-footer">
          <button type="button" class="btn-secondary" id="esign-modal-cancel">Cancel</button>
          <button type="submit" class="btn-primary" id="esign-modal-submit">Sign</button>
        </div>
      </form>
    `;
    document.body.appendChild(overlay);
    document.body.appendChild(modal);

    overlay.addEventListener("click", close);
    el("esign-modal-close").addEventListener("click", close);
    el("esign-modal-cancel").addEventListener("click", close);
    el("esign-form").addEventListener("submit", handleSubmit);
  }

  let _onConfirm = null;

  function open(options) {
    options = options || {};
    ensureMarkup();
    _onConfirm = options.onConfirm || null;

    const user = window.PharmaAuth && window.PharmaAuth.getUser ? window.PharmaAuth.getUser() : null;
    el("esign-user-name").textContent = (user && (user.display_name || user.email)) || "";
    el("esign-user-role").textContent = (user && user.role) || "";
    el("esign-user-department").textContent = (options.department || (user && user.department) || "") || "—";
    el("esign-datetime").textContent = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";

    el("esign-meaning").value = MEANINGS.includes(options.meaning) ? options.meaning : "Approved";
    el("esign-reason").value = "";
    el("esign-password").value = "";
    el("esign-error").style.display = "none";

    el("esign-modal").classList.add("open");
    el("esign-modal-overlay").classList.add("open");
  }

  function close() {
    const modal = el("esign-modal");
    const overlay = el("esign-modal-overlay");
    if (modal) modal.classList.remove("open");
    if (overlay) overlay.classList.remove("open");
    _onConfirm = null;
  }

  async function handleSubmit(evt) {
    evt.preventDefault();
    const password = el("esign-password").value;
    const meaning = el("esign-meaning").value;
    const reason = el("esign-reason").value.trim();
    const errorEl = el("esign-error");
    errorEl.style.display = "none";

    if (!password || !reason) {
      errorEl.textContent = "Password and reason are both required.";
      errorEl.style.display = "block";
      return;
    }

    const submitBtn = el("esign-modal-submit");
    submitBtn.disabled = true;
    try {
      if (_onConfirm) await _onConfirm({ password, meaning, reason });
      close();
    } catch (err) {
      errorEl.textContent = (err && err.message) || "Signature failed.";
      errorEl.style.display = "block";
    } finally {
      submitBtn.disabled = false;
    }
  }

  window.PharmaESign = { open, close };
})();
