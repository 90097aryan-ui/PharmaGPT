/* dashboard.js — Home Dashboard (v0.8) */

(function () {

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso.replace(" ", "T"));
    if (isNaN(d)) return iso;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function fmtDateShort(iso) {
    if (!iso) return "—";
    const d = new Date(iso.replace(" ", "T"));
    if (isNaN(d)) return iso;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function daysUntil(iso) {
    if (!iso) return null;
    const now  = new Date();
    const then = new Date(iso);
    return Math.round((then - now) / 86400000);
  }

  function truncate(s, n) {
    if (!s) return "";
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  const ACTIVITY_LABELS = {
    audit:    { dot: "dash-dot-audit",    label: "Audit" },
    document: { dot: "dash-dot-document", label: "Doc"   },
    kb:       { dot: "dash-dot-kb",       label: "KB"    },
    protocol: { dot: "dash-dot-protocol", label: "Proto" },
  };

  // ── Render functions ─────────────────────────────────────────────────────────

  function renderStats(counts) {
    document.getElementById("dash-stat-projects").textContent = counts.projects       ?? 0;
    document.getElementById("dash-stat-val").textContent      = counts.val_projects   ?? 0;
    document.getElementById("dash-stat-kb").textContent       = counts.kb_documents   ?? 0;
    document.getElementById("dash-stat-proto").textContent    = counts.protocols_generated ?? 0;
    document.getElementById("dash-stat-capa").textContent     = counts.pending_capas  ?? 0;
    document.getElementById("dash-stat-dev").textContent      = counts.pending_deviations ?? 0;

    const capaSub = document.getElementById("dash-stat-capa-sub");
    if (capaSub) {
      const n = counts.pending_capas ?? 0;
      capaSub.textContent = n > 0 ? "Needs attention" : "All caught up";
      capaSub.classList.toggle("is-attention", n > 0);
    }
    const devSub = document.getElementById("dash-stat-dev-sub");
    if (devSub) {
      const n = counts.pending_deviations ?? 0;
      devSub.textContent = n > 0 ? "Needs attention" : "All caught up";
      devSub.classList.toggle("is-attention", n > 0);
    }
  }

  function renderActivity(items) {
    const el = document.getElementById("dash-activity-body");
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

  function renderRecentProjects(projects) {
    const el = document.getElementById("dash-projects-body");
    if (!projects || !projects.length) {
      if (window.PharmaUI) {
        window.PharmaUI.emptyState(el, {
          icon: "folder-plus", title: "No projects yet",
          message: "Create your first validation project to get started.",
          actionLabel: "New Project",
          onAction: () => { const b = document.getElementById("btn-new-project"); if (b) b.click(); },
        });
      } else {
        el.innerHTML = '<div class="dash-empty">No projects yet. Create one from the sidebar.</div>';
      }
      return;
    }
    el.innerHTML = projects.map(p => `
      <div class="dash-proj-row" onclick="switchToProject(${p.id})">
        <div class="dash-proj-icon"><span class=\'icon\' data-lucide=\'folder\'></span></div>
        <div class="dash-proj-info">
          <div class="dash-proj-name">${truncate(p.name, 40)}</div>
          <div class="dash-proj-meta">${p.equipment_name || "—"} · ${fmtDate(p.created_at)}</div>
        </div>
        ${p.validation_type ? `<span class="dash-proj-badge">${p.validation_type}</span>` : ""}
      </div>`).join("");
  }

  function renderUpcoming(reviews, validations) {
    const el = document.getElementById("dash-upcoming-body");
    const rows = [];

    if (reviews && reviews.length) {
      rows.push('<div style="font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">KB Reviews</div>');
      reviews.forEach(r => {
        const days = daysUntil(r.review_date);
        const soon = days !== null && days <= 30;
        rows.push(`
          <div class="dash-review-row">
            <div class="dash-review-info">
              <div class="dash-review-title">${truncate(r.title, 42)}</div>
              <div class="dash-review-meta">${r.folder} · v${r.doc_version || "1.0"}</div>
            </div>
            <div class="dash-review-date${soon ? " soon" : ""}">${fmtDateShort(r.review_date)}</div>
          </div>`);
      });
    }

    if (validations && validations.length) {
      if (rows.length) rows.push('<div style="height:10px"></div>');
      rows.push('<div style="font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">Validation Targets</div>');
      validations.forEach(v => {
        rows.push(`
          <div class="dash-val-row">
            <div class="dash-val-info">
              <div class="dash-val-name">${truncate(v.name, 38)}</div>
              <div class="dash-val-meta">${v.validation_type || "—"} · ${v.status}</div>
            </div>
            <div class="dash-val-date">${fmtDateShort(v.target_date)}</div>
          </div>`);
      });
    }

    if (!rows.length) {
      if (window.PharmaUI) {
        window.PharmaUI.emptyState(el, { icon: "calendar-clock", title: "Nothing upcoming", message: "KB review dates and validation targets will appear here as they're scheduled." });
      } else {
        el.innerHTML = '<div class="dash-empty">No upcoming reviews or target dates.</div>';
      }
    } else {
      el.innerHTML = rows.join("");
    }
  }

  function renderConversations(convs) {
    const el = document.getElementById("dash-convs-body");
    if (!convs || !convs.length) {
      if (window.PharmaUI) {
        window.PharmaUI.emptyState(el, {
          icon: "message-square", title: "No conversations yet",
          message: "Ask the AI Assistant a question to get started.",
          actionLabel: "Open AI Assistant",
          onAction: () => { const b = document.getElementById("nav-chat"); if (b) b.click(); },
        });
      } else {
        el.innerHTML = '<div class="dash-empty">No AI conversations yet. Start chatting!</div>';
      }
      return;
    }
    el.innerHTML = convs.map(c => `
      <div class="dash-conv-row">
        <div class="dash-conv-proj">${truncate(c.project_name, 36)}</div>
        <div class="dash-conv-snippet">${truncate(c.snippet, 140)}</div>
        <div class="dash-conv-time">${fmtDate(c.created_at)}</div>
      </div>`).join("");
  }

  function renderHealth(h) {
    const el = document.getElementById("dash-health-body");
    if (!h) { el.innerHTML = ""; return; }

    const errClass = h.extracted_error > 0 ? "warn" : "ok";
    el.innerHTML = `
      <div class="dash-health-grid">
        <div class="dash-health-cell">
          <div class="dash-health-val">${h.total_docs ?? 0}</div>
          <div class="dash-health-label">Uploaded Files</div>
        </div>
        <div class="dash-health-cell">
          <div class="dash-health-val ok">${h.extracted_ok ?? 0}</div>
          <div class="dash-health-label">Extracted OK</div>
        </div>
        <div class="dash-health-cell">
          <div class="dash-health-val ${errClass}">${h.extracted_error ?? 0}</div>
          <div class="dash-health-label">Extraction Errors</div>
        </div>
        <div class="dash-health-cell">
          <div class="dash-health-val ok">${h.kb_extracted_ok ?? 0}</div>
          <div class="dash-health-label">KB Extracted</div>
        </div>
        <div class="dash-health-cell">
          <div class="dash-health-val">${h.total_messages ?? 0}</div>
          <div class="dash-health-label">Chat Messages</div>
        </div>
        <div class="dash-health-cell">
          <div class="dash-health-val">${h.audit_entries ?? 0}</div>
          <div class="dash-health-label">Audit Entries</div>
        </div>
      </div>`;
  }

  // ── Suite Overview cards (Batch 2) ───────────────────────────────────────────
  // All values come from pre-existing dashboard aggregate endpoints
  // (qms/dashboard, urs/dashboard, qual/dashboard, report/dashboard) and a
  // plain GET /equipment list (counted client-side) — no new backend calls.

  function setStatSub(id, text, attention) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("is-attention", !!attention);
  }

  function renderEquipmentCount(count) {
    document.getElementById("dash-stat-equipment").textContent = count ?? 0;
    setStatSub("dash-stat-equipment-sub", "In the equipment library");
  }

  function renderQmsSummaryCards(summary) {
    if (!summary) return;
    document.getElementById("dash-stat-documents").textContent = summary.total_documents ?? 0;
    const dueForReview = summary.docs_due_for_review ?? 0;
    setStatSub("dash-stat-documents-sub",
      dueForReview > 0 ? `${dueForReview} due for review` : "None due for review",
      dueForReview > 0);

    document.getElementById("dash-stat-changes").textContent = summary.total_changes ?? 0;
    const pendingChanges = summary.pending_change_approvals ?? 0;
    setStatSub("dash-stat-changes-sub",
      pendingChanges > 0 ? `${pendingChanges} pending approval` : "None pending approval",
      pendingChanges > 0);
  }

  function renderValidationStatus(urs, qual, report) {
    const pending =
      (urs && urs.pending_approval || 0) +
      (qual && qual.pending_approvals || 0) +
      (report && report.under_review || 0);
    document.getElementById("dash-stat-validation-status").textContent = pending;
    setStatSub("dash-stat-validation-status-sub",
      pending > 0 ? "Awaiting review or approval" : "All caught up",
      pending > 0);
  }

  function loadSuiteOverview() {
    fetch("/equipment")
      .then(r => r.ok ? r.json() : [])
      .then(list => renderEquipmentCount(Array.isArray(list) ? list.length : 0))
      .catch(() => renderEquipmentCount(null));

    fetch("/qms/dashboard")
      .then(r => r.ok ? r.json() : null)
      .then(data => renderQmsSummaryCards(data && data.summary))
      .catch(() => {});

    Promise.all([
      fetch("/urs/dashboard").then(r => r.ok ? r.json() : null).catch(() => null),
      fetch("/qual/dashboard").then(r => r.ok ? r.json() : null).catch(() => null),
      fetch("/report/dashboard").then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([urs, qual, report]) => renderValidationStatus(urs, qual, report));
  }

  // ── Favorites / Recent Items (Batch 5) ───────────────────────────────────────
  // Both read browser-local storage only (favorites.js / recent_items.js) —
  // no fetch, no backend. Sections hide themselves entirely when empty.

  const TYPE_ICONS = {
    projects: "folder", equipment: "wrench", sops: "clipboard-list",
    validation_docs: "check-circle-2", kb_documents: "library",
    capa: "repeat", deviations: "alert-triangle", change_control: "git-pull-request",
    documents: "file-text", urs: "file-check", risk: "shield-alert",
    qual: "microscope", report: "file-check-2",
  };

  function navigateToItem(type, id) {
    switch (type) {
      case "projects": if (window.switchToProject) window.switchToProject(id); break;
      case "equipment": if (window.eqOpenProfile) window.eqOpenProfile(id, "library"); break;
      case "sops": case "validation_docs": case "kb_documents":
        if (window.showView) window.showView("view-kb");
        if (window.kbSelectDoc) window.kbSelectDoc(id);
        break;
      case "capa":
        if (window.showView) window.showView("view-qms-capa");
        if (window.qmsCapaOpenDetail) window.qmsCapaOpenDetail(id);
        break;
      case "deviations":
        if (window.showView) window.showView("view-qms-deviations");
        if (window.qmsDevOpenDetail) window.qmsDevOpenDetail(id);
        break;
      case "change_control":
        if (window.showView) window.showView("view-qms-change-control");
        if (window.qmsCCOpenDetail) window.qmsCCOpenDetail(id);
        break;
      case "documents":
        if (window.showView) window.showView("view-qms-documents");
        if (window.qmsDocOpenDetail) window.qmsDocOpenDetail(id);
        break;
      case "urs": if (window.openURS) window.openURS(id); break;
      case "risk": if (window.openAssessment) window.openAssessment(id); break;
      case "qual":
        if (window.showView) window.showView("view-qual");
        if (window.qualShowDetail) window.qualShowDetail(id);
        break;
      case "report":
        if (window.showView) window.showView("view-report");
        if (window.openReport) window.openReport(id);
        break;
    }
  }

  function renderFavorites() {
    const card = document.getElementById("dash-favorites-card");
    const body = document.getElementById("dash-favorites-body");
    if (!card || !body || !window.PharmaFavorites) return;

    const items = window.PharmaFavorites.getAllFlat();
    if (!items.length) { card.style.display = "none"; return; }

    card.style.display = "flex";
    body.innerHTML = items.slice(0, 8).map(item => `
      <div class="dash-proj-row" data-type="${item.type}" data-id="${item.id}">
        <div class="dash-proj-icon"><span class='icon' data-lucide='${TYPE_ICONS[item.type] || "star"}'></span></div>
        <div class="dash-proj-info">
          <div class="dash-proj-name">${truncate(item.title || "Untitled", 40)}</div>
          <div class="dash-proj-meta">${truncate(item.meta || "", 40)}</div>
        </div>
      </div>`).join("");

    body.querySelectorAll("[data-type]").forEach(row => {
      row.addEventListener("click", () => navigateToItem(row.dataset.type, row.dataset.id));
    });
    if (window.refreshIcons) window.refreshIcons();
  }

  function renderRecentItems() {
    const card = document.getElementById("dash-recent-items-card");
    const body = document.getElementById("dash-recent-items-body");
    if (!card || !body || !window.PharmaRecent) return;

    const items = window.PharmaRecent.getRecent(8);
    if (!items.length) { card.style.display = "none"; return; }

    card.style.display = "flex";
    body.innerHTML = items.map(item => `
      <div class="dash-proj-row" data-type="${item.type}" data-id="${item.id}">
        <div class="dash-proj-icon"><span class='icon' data-lucide='${TYPE_ICONS[item.type] || "clock"}'></span></div>
        <div class="dash-proj-info">
          <div class="dash-proj-name">${truncate(item.title || "Untitled", 40)}</div>
          <div class="dash-proj-meta">${item.action === "edited" ? "Edited" : "Opened"} · ${fmtDateShort(item.viewedAt)}</div>
        </div>
      </div>`).join("");

    body.querySelectorAll("[data-type]").forEach(row => {
      row.addEventListener("click", () => navigateToItem(row.dataset.type, row.dataset.id));
    });
    if (window.refreshIcons) window.refreshIcons();
  }

  // ── Navigate to project from Recent Projects card ────────────────────────────
  // PharmaGPT v1.0 Module 3: opens the same unified Project Workspace a
  // sidebar click would (window.selectProject fetches nothing itself, so we
  // fetch the full project record by ID first — the Dashboard card only
  // carries the ID).

  window.switchToProject = async function (projectId) {
    try {
      const res = await fetch(`/projects/${projectId}`);
      if (!res.ok) return;
      const project = await res.json();
      if (window.selectProject) window.selectProject(project);
    } catch { /* project fetch failed — stay on Dashboard */ }
  };

  // ── Load ─────────────────────────────────────────────────────────────────────

  function renderAvgScore(avg, count) {
    const el = document.getElementById("dash-stat-score");
    if (!el) return;
    if (count === 0) {
      el.textContent = "—";
      el.title = "No documents reviewed yet this session";
      return;
    }
    el.textContent = avg.toFixed(1);
    el.title = `Average over ${count} document(s) reviewed this session`;
    // Colour the card by score band
    const card = el.closest(".dash-stat-card");
    if (card) {
      card.style.borderTop = avg >= 85
        ? "3px solid #5F8A61"
        : avg >= 70 ? "3px solid #C59A41" : "3px solid #A8544F";
    }
  }

  window.loadDashboard = function () {
    // Show loading state in all cards
    ["dash-activity-body", "dash-projects-body", "dash-upcoming-body",
     "dash-convs-body", "dash-health-body"].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      if (window.PharmaUI) window.PharmaUI.skeleton(el, { variant: "rows", rows: 3 });
      else el.innerHTML = '<div class="dash-loading">Loading…</div>';
    });

    fetch("/dashboard/stats")
      .then(r => r.json())
      .then(data => {
        renderStats(data.counts || {});
        renderActivity(data.recent_activity);
        renderRecentProjects(data.recent_projects);
        renderUpcoming(data.upcoming_reviews, data.upcoming_validations);
        renderConversations(data.recent_conversations);
        renderHealth(data.system_health);
      })
      .catch(() => {
        ["dash-activity-body", "dash-projects-body", "dash-upcoming-body", "dash-convs-body"].forEach(id => {
          const el = document.getElementById(id);
          if (!el) return;
          if (window.PharmaUI) window.PharmaUI.errorState(el, { message: "Failed to load dashboard data.", onRetry: window.loadDashboard });
          else el.innerHTML = '<div class="dash-empty">Failed to load.</div>';
        });
        const healthEl = document.getElementById("dash-health-body");
        if (healthEl) {
          if (window.PharmaUI) window.PharmaUI.errorState(healthEl, { message: "Failed to load dashboard data.", onRetry: window.loadDashboard });
          else healthEl.innerHTML = '<div class="dash-empty">Failed to load.</div>';
        }
      });

    // Fetch avg validation score independently (session cache; may be 0 initially)
    fetch("/dashboard/validation-score")
      .then(r => r.json())
      .then(d => renderAvgScore(d.avg_score || 0, d.doc_count || 0))
      .catch(() => {});

    loadSuiteOverview();
    renderFavorites();
    renderRecentItems();
  };

  // Auto-load when the page opens (dashboard is the default view)
  document.addEventListener("DOMContentLoaded", () => {
    window.loadDashboard();
  });

})();
