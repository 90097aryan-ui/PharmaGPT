/* search.js — Phase 5: Global federated search.
 *
 * Fires parallel fetches against existing, already-shipped list endpoints
 * that already accept a keyword/query filter (confirmed by reading each
 * routes/*.py file — see the SOURCES table below for the exact param each
 * one accepts) and renders one grouped dropdown. No new backend route, no
 * new query param, no semantic/AI search — purely client-side aggregation
 * of endpoints that already exist and are already used elsewhere in the
 * app. GET /projects has no server-side keyword filter, so Projects are
 * filtered client-side after fetching the (small, per-company) list.
 *
 * Click-through reuses each screen's own existing "open this record"
 * function — none of these were invented for search; every one is already
 * called by that suite's own list-row onclick.
 */

(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function safeJson(res) {
    return res.ok ? res.json().catch(() => []) : Promise.resolve([]);
  }

  const SOURCES = [
    {
      key: "projects", label: "Projects", icon: "folder",
      fetch: (q) => fetch("/projects").then(safeJson).then(list =>
        (Array.isArray(list) ? list : []).filter(p =>
          (p.name || "").toLowerCase().includes(q.toLowerCase())).slice(0, 5)),
      title: r => r.name, meta: r => r.equipment_name || "",
      open: r => { if (window.switchToProject) window.switchToProject(r.id); },
    },
    {
      key: "equipment", label: "Equipment", icon: "wrench",
      fetch: (q) => fetch("/equipment/search?q=" + encodeURIComponent(q)).then(safeJson),
      title: r => r.name, meta: r => r.project_name || r.manufacturer || "",
      open: r => { if (window.eqOpenProfile) window.eqOpenProfile(r.id, "library"); },
    },
    {
      key: "kb", label: "Knowledge Base", icon: "library",
      fetch: (q) => fetch("/kb/documents?keyword=" + encodeURIComponent(q)).then(safeJson),
      title: r => r.title, meta: r => r.folder || "",
      open: r => { if (window.showView) window.showView("view-kb"); if (window.kbSelectDoc) window.kbSelectDoc(r.id); },
    },
    {
      key: "capa", label: "CAPA", icon: "repeat",
      fetch: (q) => fetch("/qms/capa?q=" + encodeURIComponent(q)).then(safeJson),
      title: r => r.title, meta: r => r.capa_number || "",
      open: r => { if (window.showView) window.showView("view-qms-capa"); if (window.qmsCapaOpenDetail) window.qmsCapaOpenDetail(r.id); },
    },
    {
      key: "deviations", label: "Deviations", icon: "alert-triangle",
      fetch: (q) => fetch("/qms/deviations?q=" + encodeURIComponent(q)).then(safeJson),
      title: r => r.title, meta: r => r.deviation_number || "",
      open: r => { if (window.showView) window.showView("view-qms-deviations"); if (window.qmsDevOpenDetail) window.qmsDevOpenDetail(r.id); },
    },
    {
      key: "change_control", label: "Change Control", icon: "git-pull-request",
      fetch: (q) => fetch("/qms/change-control?q=" + encodeURIComponent(q)).then(safeJson),
      title: r => r.title, meta: r => r.cc_number || "",
      open: r => { if (window.showView) window.showView("view-qms-change-control"); if (window.qmsCCOpenDetail) window.qmsCCOpenDetail(r.id); },
    },
    {
      key: "documents", label: "Documents", icon: "file-text",
      fetch: (q) => fetch("/qms/documents?q=" + encodeURIComponent(q)).then(safeJson),
      title: r => r.title, meta: r => r.doc_number || "",
      open: r => { if (window.showView) window.showView("view-qms-documents"); if (window.qmsDocOpenDetail) window.qmsDocOpenDetail(r.id); },
    },
    {
      key: "urs", label: "URS", icon: "file-check",
      fetch: (q) => fetch("/urs/?q=" + encodeURIComponent(q)).then(safeJson),
      title: r => r.title, meta: r => r.equipment_name || "",
      open: r => { if (window.openURS) window.openURS(r.id); },
    },
    {
      key: "risk", label: "Risk Assessments", icon: "shield-alert",
      fetch: (q) => fetch("/risk/assessments?q=" + encodeURIComponent(q)).then(safeJson),
      title: r => r.title, meta: r => r.assessment_type || "",
      open: r => { if (window.openAssessment) window.openAssessment(r.id); },
    },
    {
      key: "qual", label: "Qualification", icon: "microscope",
      fetch: (q) => fetch("/qual/?q=" + encodeURIComponent(q)).then(safeJson),
      title: r => r.title, meta: r => r.equipment_name || "",
      open: r => { if (window.showView) window.showView("view-qual"); if (window.qualShowDetail) window.qualShowDetail(r.id); },
    },
    {
      key: "report", label: "Validation Reports", icon: "file-check-2",
      fetch: (q) => fetch("/report/?q=" + encodeURIComponent(q)).then(safeJson),
      title: r => r.title, meta: r => r.equipment_name || "",
      open: r => { if (window.showView) window.showView("view-report"); if (window.openReport) window.openReport(r.id); },
    },
  ];

  let debounceTimer = null;
  let requestSeq = 0;

  function renderResults(container, groups, query) {
    const nonEmpty = groups.filter(g => g.items.length);
    if (!nonEmpty.length) {
      container.innerHTML = `<div class="hdr-search-empty">No results for "${esc(query)}"</div>`;
      return;
    }
    container.innerHTML = nonEmpty.map(g => `
      <div class="hdr-search-group-label">${esc(g.label)}</div>
      ${g.items.map(item => `
        <div class="hdr-search-result" data-source="${g.key}" data-id="${item.id}">
          <span class="hdr-search-result-icon icon" data-lucide="${g.icon}"></span>
          <div>
            <div class="hdr-search-result-title">${esc(g.title(item))}</div>
            ${g.meta(item) ? `<div class="hdr-search-result-meta">${esc(g.meta(item))}</div>` : ""}
          </div>
        </div>`).join("")}
    `).join("");

    if (window.refreshIcons) window.refreshIcons();

    container.querySelectorAll(".hdr-search-result").forEach(row => {
      row.addEventListener("click", () => {
        const source = SOURCES.find(s => s.key === row.dataset.source);
        const group = nonEmpty.find(g => g.key === row.dataset.source);
        const item = group && group.items.find(i => String(i.id) === row.dataset.id);
        if (source && item) source.open(item);
        closeResults(container);
        const input = document.getElementById("hdr-search-input");
        if (input) input.blur();
      });
    });
  }

  function closeResults(container) {
    container.style.display = "none";
    container.innerHTML = "";
  }

  function runSearch(query, container) {
    const mySeq = ++requestSeq;
    container.innerHTML = `<div class="hdr-search-hint">Searching…</div>`;
    container.style.display = "block";

    Promise.all(SOURCES.map(s =>
      s.fetch(query)
        .then(items => ({ key: s.key, label: s.label, icon: s.icon, title: s.title, meta: s.meta, items: (items || []).slice(0, 5) }))
        .catch(() => ({ key: s.key, label: s.label, icon: s.icon, title: s.title, meta: s.meta, items: [] }))
    )).then(groups => {
      if (mySeq !== requestSeq) return; // a newer query superseded this one
      renderResults(container, groups, query);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("hdr-search-input");
    const container = document.getElementById("hdr-search-results");
    if (!input || !container) return;

    input.addEventListener("input", () => {
      const query = input.value.trim();
      clearTimeout(debounceTimer);
      if (query.length < 2) {
        closeResults(container);
        return;
      }
      debounceTimer = setTimeout(() => runSearch(query, container), 300);
    });

    input.addEventListener("focus", () => {
      if (input.value.trim().length >= 2 && container.innerHTML) container.style.display = "block";
    });

    document.addEventListener("click", (evt) => {
      if (!evt.target.closest("#hdr-search")) closeResults(container);
    });

    input.addEventListener("keydown", (evt) => {
      if (evt.key === "Escape") { closeResults(container); input.blur(); }
    });
  });
})();
