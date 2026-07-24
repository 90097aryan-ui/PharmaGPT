// projects.js — manages the Projects panel: list, create, select, delete.
// Loaded before chat.js so that activeProject is available when chat.js initialises.

// ── State ─────────────────────────────────────────────────────────────────────

// The currently selected project object ({ id, name, equipment_name, ... })
// null means no project is selected and chat is blocked.
window.activeProject = null;

// ── DOM refs ──────────────────────────────────────────────────────────────────

const projectListEl    = document.getElementById("project-list");
const activeBannerEl   = document.getElementById("active-project-banner");
const activeProjNameEl = document.getElementById("active-project-name");
const activeProjMetaEl = document.getElementById("active-project-meta");
const newProjectBtn    = document.getElementById("btn-new-project");
const modal            = document.getElementById("project-modal");
const modalOverlay     = document.getElementById("modal-overlay");
const modalForm        = document.getElementById("project-form");
const modalCloseBtn    = document.getElementById("modal-close");
const modalCancelBtn   = document.getElementById("modal-cancel");
const modalSaveBtn     = document.getElementById("modal-save");

// ── Modal open / close ────────────────────────────────────────────────────────

function openModal() {
  modalForm.reset();
  modal.classList.add("open");
  modalOverlay.classList.add("open");
  document.getElementById("proj-name").focus();
}

function closeModal() {
  modal.classList.remove("open");
  modalOverlay.classList.remove("open");
}

newProjectBtn.addEventListener("click", openModal);
modalCloseBtn.addEventListener("click", closeModal);
modalCancelBtn.addEventListener("click", closeModal);
// Click outside the modal to close
modalOverlay.addEventListener("click", closeModal);

// ── Load and render project list ──────────────────────────────────────────────

async function loadProjects() {
  try {
    const res = await fetch("/projects");
    const projects = await res.json();
    renderProjectList(projects);
  } catch {
    projectListEl.innerHTML =
      '<p style="color:rgba(255,255,255,0.35);font-size:12px;padding:8px 16px">Could not load projects.</p>';
  }
}

function renderProjectList(projects) {
  projectListEl.innerHTML = "";

  if (projects.length === 0) {
    projectListEl.innerHTML =
      '<p style="color:rgba(255,255,255,0.30);font-size:12px;padding:4px 16px;font-style:italic">No projects yet.</p>';
    return;
  }

  projects.forEach(p => {
    const item = document.createElement("div");
    item.className = "project-item";
    item.dataset.id = p.id;

    // Highlight if this is the active project
    if (window.activeProject && window.activeProject.id === p.id) {
      item.classList.add("active");
    }

    // Validation type badge
    const badge = p.validation_type
      ? `<span class="proj-badge">${p.validation_type}</span>`
      : "";

    // Only company_admin can delete a project (backend-enforced); hide the
    // button for other roles instead of showing an action that will always
    // be rejected with no visible feedback.
    const currentUser = window.PharmaAuth && window.PharmaAuth.getUser();
    const canDelete = currentUser && currentUser.role === "company_admin";
    const deleteBtn = canDelete
      ? `<button class="proj-delete-btn" data-id="${p.id}" title="Delete project"><span class=\'icon\' data-lucide=\'trash-2\'></span></button>`
      : "";

    const isFav = window.PharmaFavorites && window.PharmaFavorites.isFavorite("projects", p.id);
    const favBtn = window.PharmaFavorites
      ? `<button class="proj-fav-btn${isFav ? " is-fav" : ""}" data-id="${p.id}" title="${isFav ? "Remove from Favorites" : "Add to Favorites"}" aria-label="${isFav ? "Remove from Favorites" : "Add to Favorites"}" aria-pressed="${isFav}"><span class=\'icon\' data-lucide=\'star\'></span></button>`
      : "";

    item.innerHTML = `
      <div class="proj-item-left">
        <div class="proj-icon"><span class=\'icon\' data-lucide=\'folder\'></span></div>
        <div class="proj-item-info">
          <div class="proj-item-name">${escapeHtml(p.name)}</div>
          <div class="proj-item-sub">${escapeHtml(p.equipment_name || p.department || "—")}</div>
        </div>
      </div>
      <div class="proj-item-right">
        ${badge}
        ${favBtn}
        ${deleteBtn}
      </div>
    `;

    // Select project on click (but not on the delete/favorite button)
    item.addEventListener("click", (e) => {
      if (e.target.closest(".proj-delete-btn") || e.target.closest(".proj-fav-btn")) return;
      selectProject(p);
    });

    // Delete button
    item.querySelector(".proj-delete-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      confirmDeleteProject(p);
    });

    // Favorite toggle
    item.querySelector(".proj-fav-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      window.PharmaFavorites.toggleFavorite("projects", p.id, { title: p.name, meta: p.equipment_name || "" });
      renderProjectList(projects);
    });

    projectListEl.appendChild(item);
  });
}

// ── Select a project ──────────────────────────────────────────────────────────

async function selectProject(project) {
  window.activeProject = project;
  if (window.PharmaRecent) window.PharmaRecent.recordOpened("projects", project.id, project.name, project.equipment_name || "");

  // Update the active project banner above the chat
  activeProjNameEl.textContent = project.name;
  const meta = [
    project.equipment_name,
    project.manufacturer,
    project.department,
    project.validation_type,
  ].filter(Boolean).join("  ·  ");
  activeProjMetaEl.textContent = meta || "No additional details";
  activeBannerEl.style.display = "flex";

  // Re-render the sidebar list to show the highlighted item
  await loadProjects();

  // Load this project's saved message history into the chat window
  await loadProjectHistory(project.id);

  // Enable the send button now that a project is selected
  document.getElementById("send-btn").disabled = false;
  document.getElementById("user-input").placeholder =
    `Ask PharmaGPT about "${project.name}"…`;

  // Show the "Use Project Documents" toggle and update its hint count
  _updateUseDocsRow(project.id);

  // PharmaGPT v1.0 Module 3 — "One Project = One Workspace": selecting a
  // project opens its unified Project Workspace directly (Equipment,
  // Documents, Risk/URS/Qualification/Report entry points, Tasks, Approvals,
  // History all live inside it now — see project_workspace.js).
  if (window.pwOpenWorkspace) window.pwOpenWorkspace(project);
}

async function loadProjectHistory(projectId) {
  // Clear the current chat window
  document.getElementById("messages").innerHTML = "";

  try {
    const res = await fetch(`/projects/${projectId}/messages`);
    const messages = await res.json();

    // Replay each saved message into the chat UI
    // appendMessage is defined in chat.js (loaded after this file)
    messages.forEach(m => {
      appendMessage(m.role === "user" ? "user" : "ai", m.content);
    });
  } catch {
    // Silently ignore — an empty chat is fine
  }
}

// ── Create project ────────────────────────────────────────────────────────────

modalForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const payload = {
    name:            document.getElementById("proj-name").value.trim(),
    equipment_name:  document.getElementById("proj-equipment").value.trim(),
    manufacturer:    document.getElementById("proj-manufacturer").value.trim(),
    department:      document.getElementById("proj-department").value.trim(),
    validation_type: document.getElementById("proj-validation-type").value,
  };

  if (!payload.name) return;

  modalSaveBtn.disabled = true;
  modalSaveBtn.textContent = "Saving…";

  try {
    const res = await fetch("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error("Failed to create project");

    const project = await res.json();
    closeModal();
    await selectProject(project);       // auto-select the new project
  } catch {
    alert("Could not create project. Please try again.");
  } finally {
    modalSaveBtn.disabled = false;
    modalSaveBtn.textContent = "Create Project";
  }
});

// ── Delete project ────────────────────────────────────────────────────────────

async function confirmDeleteProject(project) {
  if (!confirm(`Delete project "${project.name}" and all its messages? This cannot be undone.`)) return;

  try {
    const res = await fetch(`/projects/${project.id}`, { method: "DELETE" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Could not delete project.");
    }

    // If we deleted the active project, clear the banner and chat
    if (window.activeProject && window.activeProject.id === project.id) {
      window.activeProject = null;
      activeBannerEl.style.display = "none";
      document.getElementById("messages").innerHTML = "";
      document.getElementById("send-btn").disabled = true;
      document.getElementById("user-input").placeholder =
        "Select or create a project to start chatting…";
      const docsRow = document.getElementById("use-docs-row");
      if (docsRow) docsRow.style.display = "none";
    }

    await loadProjects();
  } catch (e) {
    alert(e.message || "Could not delete project. Please try again.");
  }
}

// ── Utility ───────────────────────────────────────────────────────────────────

/** Escape HTML to prevent XSS when inserting user-supplied strings into innerHTML */
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Use Documents toggle ──────────────────────────────────────────────────────

async function _updateUseDocsRow(projectId) {
  const row  = document.getElementById("use-docs-row");
  const hint = document.getElementById("use-docs-hint");
  if (!row || !hint) return;

  row.style.display = "flex";

  try {
    const res = await fetch(`/projects/${projectId}/insights`);
    if (!res.ok) return;
    const data = await res.json();
    const n = data.extracted_count || 0;
    hint.textContent = n === 0
      ? "No documents indexed yet"
      : `${n} document${n === 1 ? "" : "s"} indexed`;
  } catch {
    hint.textContent = "";
  }
}

// Exposed so dashboard.js's "Recent Projects" cards can select + open the
// same Project Workspace a sidebar click would (see switchToProject()).
window.selectProject = selectProject;

// ── Init ──────────────────────────────────────────────────────────────────────

// Load the project list as soon as the DOM is ready
document.addEventListener("DOMContentLoaded", loadProjects);
