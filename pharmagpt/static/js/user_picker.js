/**
 * static/js/user_picker.js — Shared Reviewer/Approver name-search picker.
 *
 * Extracted from static/js/qms_deviations.js's Workflow Builder approver
 * picker (the only searchable-by-name UI in the app before this change) so
 * every Reviewer/Approver/Prepared By-style field can reuse the same
 * pattern instead of a free-text <input>: a searchable text box bound to a
 * shared <datalist> of the company's active users (GET /users/directory,
 * pharmagpt/routes/users.py — display_name + optional department/
 * designation for disambiguation only, deliberately no email). The value
 * this module ever resolves to is a plain display_name (or, for
 * findByLabel(), the full {user_id, display_name, ...} directory entry) —
 * never department/designation/email.
 *
 * Two consumption patterns:
 *   - attachNamePicker(inputEl, directory): for a plain name-only field
 *     (Reviewer, Approver, Prepared By, ...) — on an exact suggestion
 *     match, collapses the input's value from the disambiguated label
 *     ("Jane Doe (QA / QA Officer)") back down to just "Jane Doe". Typing a
 *     name not in the directory is left as-is (an external/contract
 *     approver who isn't a PharmaGPT user is still a valid name).
 *   - findByLabel(typed, directory): for a field that must resolve to a
 *     real user_id (qms_deviations.js's workflow-builder approvers, which
 *     route actual approval tasks) — returns the matching entry or null,
 *     exact match only, so a mistyped/nonexistent id can never be saved.
 */
(function () {
  "use strict";

  function label(entry) {
    const meta = [entry.department, entry.designation].filter(Boolean).join(" / ");
    return meta ? `${entry.display_name} (${meta})` : entry.display_name;
  }

  async function loadDirectory() {
    try {
      const res = await fetch("/users/directory");
      if (!res.ok) return [];
      return (await res.json()) || [];
    } catch (e) {
      return []; // picker degrades to "no matches" rather than blocking the form
    }
  }

  function datalistHTML(listId, directory) {
    return `<datalist id="${listId}">
      ${directory.map(e => `<option value="${label(e).replace(/"/g, "&quot;")}"></option>`).join("")}
    </datalist>`;
  }

  function findByLabel(typed, directory) {
    const needle = (typed || "").trim();
    return directory.find(e => label(e) === needle) || null;
  }

  function attachNamePicker(inputEl, directory) {
    if (!inputEl) return;
    inputEl.addEventListener("input", () => {
      const entry = findByLabel(inputEl.value, directory);
      if (entry) inputEl.value = entry.display_name;
    });
  }

  window.UserPicker = { label, loadDirectory, datalistHTML, findByLabel, attachNamePicker };
})();
