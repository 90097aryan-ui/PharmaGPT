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
  }

  function renderActivity(items) {
    const el = document.getElementById("dash-activity-body");
    if (!items || !items.length) {
      el.innerHTML = '<div class="dash-empty">No activity yet.</div>';
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
      el.innerHTML = '<div class="dash-empty">No projects yet. Create one from the sidebar.</div>';
      return;
    }
    el.innerHTML = projects.map(p => `
      <div class="dash-proj-row" onclick="switchToProject(${p.id})">
        <div class="dash-proj-icon">📁</div>
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
      el.innerHTML = '<div class="dash-empty">No upcoming reviews or target dates.</div>';
    } else {
      el.innerHTML = rows.join("");
    }
  }

  function renderConversations(convs) {
    const el = document.getElementById("dash-convs-body");
    if (!convs || !convs.length) {
      el.innerHTML = '<div class="dash-empty">No AI conversations yet. Start chatting!</div>';
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

  // ── Navigate to project from Recent Projects card ────────────────────────────

  window.switchToProject = function (projectId) {
    // Select the project in the sidebar and switch to Chat view
    if (window.selectProject) {
      window.selectProject(projectId);
    }
    // Switch to chat view
    document.querySelectorAll(".sidebar-item[data-view]").forEach(n => n.classList.remove("active"));
    const chatNav = document.getElementById("nav-chat");
    if (chatNav) chatNav.classList.add("active");
    document.querySelectorAll("main[id^='view-']").forEach(v => {
      v.style.display = v.id === "view-chat" ? "flex" : "none";
    });
  };

  // ── Load ─────────────────────────────────────────────────────────────────────

  window.loadDashboard = function () {
    // Show loading state in all cards
    ["dash-activity-body", "dash-projects-body", "dash-upcoming-body",
     "dash-convs-body", "dash-health-body"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = '<div class="dash-loading">Loading…</div>';
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
        ["dash-activity-body", "dash-projects-body", "dash-upcoming-body",
         "dash-convs-body", "dash-health-body"].forEach(id => {
          const el = document.getElementById(id);
          if (el) el.innerHTML = '<div class="dash-empty">Failed to load.</div>';
        });
      });
  };

  // Auto-load when the page opens (dashboard is the default view)
  document.addEventListener("DOMContentLoaded", () => {
    window.loadDashboard();
  });

})();
