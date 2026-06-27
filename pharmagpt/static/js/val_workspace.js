/*
 * val_workspace.js — Validation Workspace module (v0.8 Step 1)
 *
 * Handles:
 *   - Dashboard: load/render all validation projects, stats
 *   - Create Validation Project modal
 *   - Workspace: tab switching, Overview & Equipment detail, Audit Trail
 */

(function () {
  "use strict";

  // ── State ──────────────────────────────────────────────────────────────────
  let _projects   = [];
  let _activeProj = null;

  // ── DOM refs (resolved once on init) ──────────────────────────────────────
  const $ = id => document.getElementById(id);

  // ── Init (called when the nav item is clicked) ─────────────────────────────
  function initVW() {
    loadDashboard();
  }
  window.initVW = initVW;

  // ══════════════════════════════════════════════════════════════════════════
  // DASHBOARD
  // ══════════════════════════════════════════════════════════════════════════

  async function loadDashboard() {
    try {
      const res  = await fetch("/val-projects");
      _projects  = await res.json();
      renderDashboard();
    } catch (e) {
      console.error("VW: failed to load projects", e);
    }
  }

  function renderDashboard() {
    const grid  = $("vw-project-grid");
    const empty = $("vw-empty");
    if (!grid) return;

    // Stats
    const total      = _projects.length;
    const inProgress = _projects.filter(p => p.status === "In Progress").length;
    const completed  = _projects.filter(p => p.status === "Completed").length;
    const onHold     = _projects.filter(p => p.status === "On Hold").length;
    setText("vw-stat-total",      total);
    setText("vw-stat-inprogress", inProgress);
    setText("vw-stat-completed",  completed);
    setText("vw-stat-onhold",     onHold);

    // Grid
    grid.innerHTML = "";

    if (_projects.length === 0) {
      grid.style.display  = "none";
      empty.style.display = "flex";
      return;
    }

    grid.style.display  = "grid";
    empty.style.display = "none";

    _projects.forEach(p => grid.appendChild(buildCard(p)));
  }

  function buildCard(p) {
    const card = document.createElement("div");
    card.className = "vw-project-card";
    card.dataset.id = p.id;

    const riskClass = {
      Critical: "risk-critical", High: "risk-high",
      Medium: "risk-medium",     Low:  "risk-low",
    }[p.risk_category] || "";

    const statusClass = {
      "In Progress": "status-inprogress",
      "Completed":   "status-completed",
      "On Hold":     "status-onhold",
    }[p.status] || "status-inprogress";

    const targetStr = p.target_date
      ? `🗓 ${fmtDate(p.target_date)}`
      : "";

    card.innerHTML = `
      <div class="vw-card-top">
        <div class="vw-card-name">${esc(p.name)}</div>
        <div class="vw-card-badges">
          ${p.validation_type ? `<span class="vw-badge-type">${esc(p.validation_type)}</span>` : ""}
          ${p.risk_category   ? `<span class="vw-badge-risk ${riskClass}">${esc(p.risk_category)}</span>` : ""}
        </div>
      </div>
      <div class="vw-card-meta">
        ${p.equipment_name ? `<div class="vw-card-meta-row"><span>⚙️</span>${esc(p.equipment_name)}${p.model ? ` · ${esc(p.model)}` : ""}</div>` : ""}
        ${p.department     ? `<div class="vw-card-meta-row"><span>🏢</span>${esc(p.department)}</div>` : ""}
        ${p.owner          ? `<div class="vw-card-meta-row"><span>👤</span>${esc(p.owner)}</div>` : ""}
        ${targetStr        ? `<div class="vw-card-meta-row">${targetStr}</div>` : ""}
      </div>
      <div class="vw-card-footer">
        <span class="vw-card-status ${statusClass}">${esc(p.status || "In Progress")}</span>
        <span class="vw-card-date">${fmtDatetime(p.created_at)}</span>
        <button class="vw-card-del" title="Delete project" data-id="${p.id}">🗑</button>
      </div>
    `;

    // Open workspace on card click (not delete btn)
    card.addEventListener("click", e => {
      if (e.target.closest(".vw-card-del")) return;
      openWorkspace(p.id);
    });

    card.querySelector(".vw-card-del").addEventListener("click", e => {
      e.stopPropagation();
      deleteProject(p.id, p.name);
    });

    return card;
  }

  // ══════════════════════════════════════════════════════════════════════════
  // CREATE MODAL
  // ══════════════════════════════════════════════════════════════════════════

  function openCreateModal() {
    $("vw-create-form").reset();
    $("vw-modal-overlay").classList.add("active");
    $("vw-create-modal").classList.add("active");
    $("vw-name").focus();
  }

  function closeCreateModal() {
    $("vw-modal-overlay").classList.remove("active");
    $("vw-create-modal").classList.remove("active");
  }

  async function submitCreateForm(e) {
    e.preventDefault();

    const payload = {
      name:            $("vw-name").value.trim(),
      equipment_name:  $("vw-equipment-name").value.trim(),
      equipment_id:    $("vw-equipment-id").value.trim(),
      department:      $("vw-department").value.trim(),
      manufacturer:    $("vw-manufacturer").value.trim(),
      model:           $("vw-model").value.trim(),
      location:        $("vw-location").value.trim(),
      validation_type: $("vw-validation-type").value,
      protocol_number: $("vw-protocol-number").value.trim(),
      report_number:   $("vw-report-number").value.trim(),
      owner:           $("vw-owner").value.trim(),
      approver:        $("vw-approver").value.trim(),
      target_date:     $("vw-target-date").value || null,
      risk_category:   $("vw-risk-category").value,
    };

    if (!payload.name) return;

    try {
      const res  = await fetch("/val-projects", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(payload),
      });
      const proj = await res.json();
      if (res.ok) {
        closeCreateModal();
        await loadDashboard();
        openWorkspace(proj.id);
      }
    } catch (e) {
      console.error("VW: create failed", e);
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // DELETE
  // ══════════════════════════════════════════════════════════════════════════

  async function deleteProject(id, name) {
    if (!confirm(`Delete validation project "${name}"? This cannot be undone.`)) return;
    try {
      await fetch(`/val-projects/${id}`, { method: "DELETE" });
      await loadDashboard();
    } catch (e) {
      console.error("VW: delete failed", e);
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // WORKSPACE
  // ══════════════════════════════════════════════════════════════════════════

  async function openWorkspace(id) {
    const proj = await fetchProject(id);
    if (!proj) return;
    _activeProj = proj;

    // Populate phase placeholder labels
    document.querySelectorAll(".vw-phase-placeholder").forEach(el => {
      const ph   = el.dataset.phase;
      const full = el.dataset.full;
      el.innerHTML = `
        <div class="vw-phase-block">
          <div class="vw-phase-block-icon">📋</div>
          <div class="vw-phase-block-title">${ph} — ${full}</div>
          <div class="vw-phase-block-sub">
            Document generation for this phase is coming in Step 2.<br>
            Protocol Number: <strong>${esc(proj.protocol_number || "—")}</strong>
          </div>
        </div>`;
    });

    // Top bar
    setText("vw-ws-proj-name", proj.name);
    setText("vw-ws-proj-meta",
      [proj.validation_type, proj.equipment_name, proj.department]
        .filter(Boolean).join(" · ") || "—"
    );
    const statusBadge = $("vw-ws-status-badge");
    statusBadge.textContent = proj.status || "In Progress";
    statusBadge.className   = "vw-ws-status-badge";

    populateOverview(proj);
    populateEquipment(proj);
    loadAuditTrail(proj.id);

    // Switch to first tab
    switchTab("overview");

    // Show workspace, hide dashboard
    showView("view-val-project");
  }

  async function fetchProject(id) {
    try {
      const res = await fetch(`/val-projects/${id}`);
      return res.ok ? await res.json() : null;
    } catch { return null; }
  }

  function populateOverview(p) {
    const grid = $("vw-overview-grid");
    if (!grid) return;

    grid.innerHTML = `
      <div class="vw-overview-card">
        <div class="vw-overview-card-title">Project Information</div>
        <div class="vw-kv-list">
          ${kv("Project Name",     p.name)}
          ${kv("Validation Type",  p.validation_type)}
          ${kv("Protocol No.",     p.protocol_number)}
          ${kv("Report No.",       p.report_number)}
          ${kv("Status",          p.status)}
          ${kv("Risk Category",    p.risk_category)}
          ${kv("Target Date",      p.target_date ? fmtDate(p.target_date) : "")}
        </div>
      </div>
      <div class="vw-overview-card">
        <div class="vw-overview-card-title">Equipment &amp; Location</div>
        <div class="vw-kv-list">
          ${kv("Equipment Name", p.equipment_name)}
          ${kv("Equipment ID",   p.equipment_id)}
          ${kv("Manufacturer",   p.manufacturer)}
          ${kv("Model",          p.model)}
          ${kv("Department",     p.department)}
          ${kv("Location",       p.location)}
        </div>
      </div>
      <div class="vw-overview-card">
        <div class="vw-overview-card-title">Personnel</div>
        <div class="vw-kv-list">
          ${kv("Owner",    p.owner)}
          ${kv("Approver", p.approver)}
        </div>
      </div>
      <div class="vw-overview-card">
        <div class="vw-overview-card-title">Timeline</div>
        <div class="vw-kv-list">
          ${kv("Created",     fmtDatetime(p.created_at))}
          ${kv("Target Date", p.target_date ? fmtDate(p.target_date) : "")}
        </div>
      </div>
    `;
  }

  function populateEquipment(p) {
    const grid = $("vw-equipment-grid");
    if (!grid) return;
    const cells = [
      ["Equipment Name", p.equipment_name],
      ["Equipment ID",   p.equipment_id],
      ["Manufacturer",   p.manufacturer],
      ["Model",          p.model],
      ["Department",     p.department],
      ["Location",       p.location],
    ];
    grid.innerHTML = cells.map(([label, val]) => `
      <div class="vw-info-cell">
        <div class="vw-info-cell-label">${label}</div>
        <div class="vw-info-cell-value${val ? "" : " empty"}">${esc(val) || "—"}</div>
      </div>`
    ).join("");
  }

  async function loadAuditTrail(projId) {
    const list = $("vw-audit-list");
    if (!list) return;
    try {
      const res     = await fetch(`/val-projects/${projId}/audit-trail`);
      const entries = await res.json();

      if (!entries.length) {
        list.innerHTML = `<div class="vw-audit-empty">No audit entries yet.</div>`;
        return;
      }

      list.innerHTML = entries.map(e => `
        <div class="vw-audit-entry">
          <div class="vw-audit-dot"></div>
          <div class="vw-audit-body">
            <div class="vw-audit-action">${esc(e.action)}</div>
            ${e.user_note ? `<div class="vw-audit-note">${esc(e.user_note)}</div>` : ""}
            <div class="vw-audit-time">${fmtDatetime(e.created_at)}</div>
          </div>
        </div>`
      ).join("");
    } catch (err) {
      list.innerHTML = `<div class="vw-audit-empty">Failed to load audit trail.</div>`;
    }
  }

  // ── Tab switching ──────────────────────────────────────────────────────────
  function switchTab(tabName) {
    document.querySelectorAll(".vw-tab").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.tab === tabName);
    });
    document.querySelectorAll(".vw-panel").forEach(panel => {
      panel.classList.toggle("active", panel.id === `vw-panel-${tabName}`);
    });
    if (tabName === "audit" && _activeProj) {
      loadAuditTrail(_activeProj.id);
    }
  }

  // ── Back to dashboard ──────────────────────────────────────────────────────
  function backToDashboard() {
    _activeProj = null;
    showView("view-val-workspace");
    loadDashboard();
  }

  // ══════════════════════════════════════════════════════════════════════════
  // VIEW SWITCHING HELPER
  // ══════════════════════════════════════════════════════════════════════════
  function showView(viewId) {
    document.querySelectorAll("main[id^='view-']").forEach(v => {
      v.style.display = "none";
    });
    const target = $(viewId);
    if (target) target.style.display = "flex";

    // Keep "Validation" nav item highlighted for both workspace sub-views
    document.querySelectorAll(".sidebar-item[data-view]").forEach(n => n.classList.remove("active"));
    document.querySelectorAll(".val-nav-item").forEach(n => n.classList.remove("active"));
    const navVW = $("nav-val-workspace");
    if (navVW) navVW.classList.add("active");
  }

  // ══════════════════════════════════════════════════════════════════════════
  // HELPERS
  // ══════════════════════════════════════════════════════════════════════════
  function esc(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function setText(id, val) {
    const el = $(id);
    if (el) el.textContent = val;
  }

  function kv(label, val) {
    const isEmpty = !val;
    return `<div class="vw-kv-row">
      <span class="vw-kv-label">${label}</span>
      <span class="vw-kv-value${isEmpty ? " empty" : ""}">${isEmpty ? "—" : esc(String(val))}</span>
    </div>`;
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso + (iso.includes("T") ? "" : "T00:00:00"));
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  }

  function fmtDatetime(iso) {
    if (!iso) return "";
    const d = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
    return d.toLocaleString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // WIRE UP on DOMContentLoaded
  // ══════════════════════════════════════════════════════════════════════════
  document.addEventListener("DOMContentLoaded", () => {

    // Create modal open/close
    const btnCreate   = $("vw-btn-create");
    const overlay     = $("vw-modal-overlay");
    const btnClose    = $("vw-modal-close");
    const btnCancel   = $("vw-modal-cancel");
    const form        = $("vw-create-form");

    if (btnCreate) btnCreate.addEventListener("click", openCreateModal);
    if (overlay)   overlay.addEventListener("click",   closeCreateModal);
    if (btnClose)  btnClose.addEventListener("click",  closeCreateModal);
    if (btnCancel) btnCancel.addEventListener("click", closeCreateModal);
    if (form)      form.addEventListener("submit",     submitCreateForm);

    // Tab clicks
    document.querySelectorAll(".vw-tab").forEach(btn => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    // Back button
    const backBtn = $("vw-ws-back");
    if (backBtn) backBtn.addEventListener("click", backToDashboard);

    // Note: nav-val-workspace click is handled by the inline nav script in index.html
    // which calls window.initVW(). No duplicate listener needed here.
  });

})();
