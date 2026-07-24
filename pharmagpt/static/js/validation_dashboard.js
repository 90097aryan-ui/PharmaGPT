/* validation_dashboard.js — Validation Suite's Validation Dashboard (Phase B, ALD-001).
 *
 * Every data source below is an existing, unmodified endpoint — this file
 * adds zero backend routes:
 *   GET /dashboard/stats   -> counts.projects, recent_projects, recent_activity
 *   GET /urs/dashboard     -> total / draft / under_review / pending_approval
 *   GET /qual/dashboard    -> total / completed / approved / pending_approval
 *   GET /report/dashboard  -> total / under_review / approved / released
 *   GET /risk/dashboard    -> total / in_review
 *   GET /qms/dashboard     -> unified Deviations/CAPA/Change Control summary
 *   GET /equipment         -> company equipment list (counted client-side)
 * The Approval Queue additionally calls each suite's existing filtered list
 * endpoint (?status=...) and merges the results — no new backend route.
 *
 * The Projects panel is a read-only summary only (per ALD-001 Phase B scope
 * — "an executive dashboard, not a second project workspace"). Opening or
 * creating a project reuses the existing, unmodified APIs from
 * dashboard.js (window.switchToProject) and projects.js (#btn-new-project);
 * this file does not reimplement project rendering.
 */

(function () {

  function truncate(s, n) {
    if (!s) return "";
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  function fmtDateShort(iso) {
    if (!iso) return "—";
    const d = new Date(iso.replace(" ", "T"));
    if (isNaN(d)) return iso;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  async function fetchJSON(url) {
    try {
      const res = await fetch(url);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  // ── 1. KPI Dashboard ─────────────────────────────────────────────────────

  function renderKPIs({ dashboardStats, ursStats, qualStats, reportStats, riskStats, qmsStats, equipmentCount }) {
    const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

    setText("vd-stat-projects", dashboardStats?.counts?.projects ?? "—");

    const ursOpen = ursStats ? (ursStats.draft ?? 0) + (ursStats.under_review ?? 0) : "—";
    setText("vd-stat-urs", ursOpen);

    if (qualStats && qualStats.total) {
      const doneish = (qualStats.completed ?? 0) + (qualStats.approved ?? 0);
      const pct = Math.round((doneish / qualStats.total) * 100);
      setText("vd-stat-qual", `${pct}%`);
      setText("vd-stat-qual-sub", `${doneish} of ${qualStats.total} qualifications complete`);
    } else {
      setText("vd-stat-qual", "—");
    }

    const pendingApprovals =
      (ursStats?.pending_approval ?? 0) +
      (qualStats?.pending_approval ?? 0) +
      (reportStats?.under_review ?? 0) +
      (riskStats?.in_review ?? 0) +
      (qmsStats?.summary?.pending_change_approvals ?? 0);
    setText("vd-stat-approvals", pendingApprovals);

    setText("vd-stat-reports", reportStats?.total ?? "—");
    setText("vd-stat-equipment", equipmentCount ?? "—");
  }

  // ── 2. Projects Panel (summary only) ────────────────────────────────────
  // Reuses window.switchToProject (dashboard.js) to open a project and the
  // existing #btn-new-project button to create one. Does not reimplement
  // project list rendering or fetch project data independently — it reuses
  // the recent_projects array already returned by /dashboard/stats.

  function renderProjectsSummary(recentProjects) {
    const el = document.getElementById("vd-projects-body");
    if (!el) return;
    if (!recentProjects || !recentProjects.length) {
      if (window.PharmaUI) {
        window.PharmaUI.emptyState(el, {
          icon: "folder-plus", title: "No projects yet",
          message: "Create your first validation project to get started.",
          actionLabel: "New Project",
          onAction: () => { const b = document.getElementById("btn-new-project"); if (b) b.click(); },
        });
      } else {
        el.innerHTML = '<div class="dash-empty">No projects yet.</div>';
      }
      return;
    }
    el.innerHTML = recentProjects.map(p => `
      <div class="dash-proj-row" onclick="window.switchToProject && window.switchToProject(${p.id})">
        <div class="dash-proj-icon"><span class='icon' data-lucide='folder'></span></div>
        <div class="dash-proj-info">
          <div class="dash-proj-name">${truncate(p.name, 40)}</div>
          <div class="dash-proj-meta">${p.equipment_name || "—"} · ${fmtDateShort(p.created_at)}</div>
        </div>
        ${p.validation_type ? `<span class="dash-proj-badge">${p.validation_type}</span>` : ""}
      </div>`).join("");
  }

  // ── 3. Quality & Compliance Panel ────────────────────────────────────────
  // Reuses GET /qms/dashboard verbatim (already "unified stats across
  // Document Control, Deviations, CAPA, and Change Control" per its own
  // docstring) — no new query, no new route.

  function renderQuality(qmsStats) {
    const el = document.getElementById("vd-quality-body");
    if (!el) return;
    if (!qmsStats) {
      el.innerHTML = '<div class="dash-empty">Could not load Quality &amp; Compliance data.</div>';
      return;
    }
    const s = qmsStats.summary || {};
    el.innerHTML = `
      <div class="dash-proj-row" onclick="window.showView && window.showView('view-qms-deviations')">
        <div class="dash-proj-icon"><span class='icon' data-lucide='alert-triangle'></span></div>
        <div class="dash-proj-info">
          <div class="dash-proj-name">Deviations</div>
          <div class="dash-proj-meta">${s.open_deviations ?? 0} open of ${s.total_deviations ?? 0}</div>
        </div>
      </div>
      <div class="dash-proj-row" onclick="window.showView && window.showView('view-qms-capa')">
        <div class="dash-proj-icon"><span class='icon' data-lucide='repeat'></span></div>
        <div class="dash-proj-info">
          <div class="dash-proj-name">CAPA</div>
          <div class="dash-proj-meta">${s.open_capas ?? 0} open · ${s.overdue_capas ?? 0} overdue</div>
        </div>
      </div>
      <div class="dash-proj-row" onclick="window.showView && window.showView('view-qms-change-control')">
        <div class="dash-proj-icon"><span class='icon' data-lucide='git-pull-request'></span></div>
        <div class="dash-proj-info">
          <div class="dash-proj-name">Change Control</div>
          <div class="dash-proj-meta">${s.open_changes ?? 0} open · ${s.pending_change_approvals ?? 0} pending approval</div>
        </div>
      </div>`;
  }

  // ── 4. Approval Queue ────────────────────────────────────────────────────
  // Merges each suite's existing filtered list endpoint (status=... — every
  // one of these already supports this filter, see routes/urs.py,
  // routes/qual.py, routes/report.py, routes/risk.py, routes/
  // qms_change_control.py) client-side. No new backend route.

  // `targetId` is optional (Phase C, ALD-001 orchestrator rule) — defaults to
  // this panel's own container so every existing caller is unaffected. Passed
  // explicitly by project_workspace.js to reuse this same merge logic for the
  // Project Workspace's Approvals tab, instead of duplicating it there.
  async function loadApprovalQueue(targetId) {
    const el = document.getElementById(targetId || "vd-approvals-body");
    if (!el) return;

    const [ursUR, ursPA, qualUR, qualPA, reportUR, riskIR, ccQA, ccAP] = await Promise.all([
      fetchJSON("/urs/?status=under_review"),
      fetchJSON("/urs/?status=pending_approval"),
      fetchJSON("/qual/?status=under_review"),
      fetchJSON("/qual/?status=pending_approval"),
      fetchJSON("/report/?status=under_review"),
      fetchJSON("/risk/assessments?status=In Review"),
      fetchJSON("/qms/change-control?status=QA Review"),
      fetchJSON("/qms/change-control?status=Approval"),
    ]);

    const items = [];
    const push = (rows, type, view) => (rows || []).forEach(r => items.push({ type, view, title: r.title, date: r.created_at }));
    push(ursUR, "URS", "view-urs-dashboard");
    push(ursPA, "URS", "view-urs-dashboard");
    push(qualUR, "Qualification", "view-qual");
    push(qualPA, "Qualification", "view-qual");
    push(reportUR, "Validation Report", "view-report");
    push(riskIR, "Risk Assessment", "view-risk-dashboard");
    push(ccQA, "Change Control", "view-qms-change-control");
    push(ccAP, "Change Control", "view-qms-change-control");

    if (!items.length) {
      if (window.PharmaUI) {
        window.PharmaUI.emptyState(el, { icon: "check-circle", title: "Nothing pending", message: "All caught up across the Validation Suite." });
      } else {
        el.innerHTML = '<div class="dash-empty">Nothing pending.</div>';
      }
      return;
    }

    items.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));

    el.innerHTML = items.map(item => `
      <div class="dash-proj-row" onclick="window.showView && window.showView('${item.view}')">
        <div class="dash-proj-icon"><span class='icon' data-lucide='clock'></span></div>
        <div class="dash-proj-info">
          <div class="dash-proj-name">${truncate(item.title || "Untitled", 40)}</div>
          <div class="dash-proj-meta">${item.type}</div>
        </div>
      </div>`).join("");
  }

  // ── 5. Recent Activity ───────────────────────────────────────────────────
  // Reuses GET /dashboard/stats().recent_activity verbatim (already unifies
  // qms_audit_trail, project documents, KB documents, and generated
  // documents — see database.py::get_dashboard_stats). No placeholder
  // needed; real data already exists.

  const ACTIVITY_LABELS = {
    audit:    { dot: "dash-dot-audit",    label: "Audit" },
    document: { dot: "dash-dot-document", label: "Doc"   },
    kb:       { dot: "dash-dot-kb",       label: "KB"    },
    protocol: { dot: "dash-dot-protocol", label: "Proto" },
  };

  function renderActivity(items) {
    const el = document.getElementById("vd-activity-body");
    if (!el) return;
    if (!items || !items.length) {
      if (window.PharmaUI) {
        window.PharmaUI.emptyState(el, { icon: "activity", title: "No activity yet", message: "Actions across projects, documents, and protocols will show up here." });
      } else {
        el.innerHTML = '<div class="dash-empty">No activity yet.</div>';
      }
      return;
    }
    el.innerHTML = items.map(item => {
      const meta = ACTIVITY_LABELS[item.type] || { dot: "dash-dot-document", label: item.type };
      return `
        <div class="dash-activity-item">
          <div class="dash-activity-dot ${meta.dot}"></div>
          <div class="dash-activity-body">
            <div class="dash-activity-title">${truncate(item.title, 60)}</div>
            <div class="dash-activity-ctx">${truncate(item.context, 40)}</div>
          </div>
          <div class="dash-activity-time">${fmtDateShort(item.created_at)}</div>
        </div>`;
    }).join("");
  }

  // ── Orchestration ────────────────────────────────────────────────────────

  async function loadValidationDashboard() {
    const [dashboardStats, ursStats, qualStats, reportStats, riskStats, qmsStats, equipment] = await Promise.all([
      fetchJSON("/dashboard/stats"),
      fetchJSON("/urs/dashboard"),
      fetchJSON("/qual/dashboard"),
      fetchJSON("/report/dashboard"),
      fetchJSON("/risk/dashboard"),
      fetchJSON("/qms/dashboard"),
      fetchJSON("/equipment"),
    ]);

    renderKPIs({
      dashboardStats, ursStats, qualStats, reportStats, riskStats, qmsStats,
      equipmentCount: Array.isArray(equipment) ? equipment.length : "—",
    });
    renderProjectsSummary(dashboardStats && dashboardStats.recent_projects);
    renderQuality(qmsStats);
    renderActivity(dashboardStats && dashboardStats.recent_activity);
    loadApprovalQueue(); // independent fetch set; does not block the rest
  }

  window.loadValidationDashboard = loadValidationDashboard;

  // Exposed for reuse by project_workspace.js's Approvals tab (Phase C) —
  // same merge logic, different target element, no duplicated code.
  window.loadApprovalQueue = loadApprovalQueue;

  // Load whenever the Validation Dashboard sidebar item is clicked — mirrors
  // how other suites init on their own nav click (window.initRisk,
  // window.initQual, etc.) rather than assuming the view is visible at
  // DOMContentLoaded. This listens on the existing Phase A sidebar element
  // without modifying it.
  document.addEventListener("DOMContentLoaded", function () {
    const navEl = document.getElementById("nav-validation-dashboard");
    if (navEl) navEl.addEventListener("click", loadValidationDashboard);
  });

})();
