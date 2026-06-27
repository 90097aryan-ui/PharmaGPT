// insights.js — Document Insights panel for the active project

/**
 * Load and render document insights for the active project.
 * Called by projects.js whenever the user switches to the Insights view.
 */
async function loadInsights() {
  const panel = document.getElementById("insights-panel");
  if (!panel) return;

  if (!window.activeProject) {
    panel.innerHTML = `
      <div class="insights-empty">
        <div class="insights-empty-icon">📊</div>
        <p>Select a project to view its Document Insights.</p>
      </div>`;
    return;
  }

  panel.innerHTML = `<div class="insights-loading">Loading insights…</div>`;

  try {
    const res = await fetch(`/projects/${window.activeProject.id}/insights`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderInsights(panel, data);
  } catch (err) {
    panel.innerHTML = `<div class="insights-empty"><p>Could not load insights. Please try again.</p></div>`;
  }
}

function renderInsights(panel, data) {
  const lastUpload = data.last_upload
    ? new Date(data.last_upload).toLocaleDateString("en-GB", {
        day: "2-digit", month: "short", year: "numeric",
      })
    : "—";

  // File type breakdown badges
  const typeLabels = { pdf: "PDF", docx: "DOCX", xlsx: "XLSX", txt: "TXT" };
  const typeColors = { pdf: "#E53935", docx: "#1565C0", xlsx: "#2E7D32", txt: "#757575" };

  const typeBadges = Object.entries(data.file_types || {})
    .map(([ext, cnt]) => `
      <span class="type-badge" style="background:${typeColors[ext] || "#546E7A"}">
        ${typeLabels[ext] || ext.toUpperCase()} × ${cnt}
      </span>`)
    .join("");

  const extractionPct = data.document_count > 0
    ? Math.round((data.extracted_count / data.document_count) * 100)
    : 0;

  panel.innerHTML = `
    <div class="insights-header">
      <h2>📊 Document Insights</h2>
      <p class="insights-project-name">${window.activeProject.name}</p>
    </div>

    <div class="insights-stats-grid">
      <div class="insights-stat-card">
        <div class="stat-value">${data.document_count}</div>
        <div class="stat-label">Documents</div>
      </div>
      <div class="insights-stat-card">
        <div class="stat-value">${data.total_pages.toLocaleString()}</div>
        <div class="stat-label">Pages</div>
      </div>
      <div class="insights-stat-card">
        <div class="stat-value">${formatWords(data.total_words)}</div>
        <div class="stat-label">Words Extracted</div>
      </div>
      <div class="insights-stat-card">
        <div class="stat-value">${lastUpload}</div>
        <div class="stat-label">Last Upload</div>
      </div>
    </div>

    <div class="insights-section">
      <h3>File Types</h3>
      <div class="insights-types">
        ${typeBadges || '<span class="insights-none">No documents yet</span>'}
      </div>
    </div>

    <div class="insights-section">
      <h3>AI Extraction Status</h3>
      <div class="insights-progress-row">
        <div class="insights-progress-bar">
          <div class="insights-progress-fill" style="width:${extractionPct}%"></div>
        </div>
        <span class="insights-progress-label">${data.extracted_count} / ${data.document_count} indexed</span>
      </div>
      <p class="insights-hint">
        Indexed documents are searched when <strong>Use Project Documents</strong> is enabled in chat.
      </p>
    </div>

    <div class="insights-section">
      <button class="btn-refresh-insights" onclick="loadInsights()">↻ Refresh</button>
    </div>
  `;
}

function formatWords(n) {
  if (!n) return "0";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return n.toString();
}

// Expose for projects.js to call when switching to the insights view
window.loadInsights = loadInsights;
