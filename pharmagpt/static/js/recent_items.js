/**
 * static/js/recent_items.js — Phase 5: browser-local Recently Opened /
 * Recently Edited tracking.
 *
 * Same storage convention as auth.js/favorites.js. A capped ring buffer,
 * browser localStorage only — no backend endpoint. Hooked at each suite's
 * existing "open this record" / "save this record" call site with a
 * single added line; this file owns only the storage + read API.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "pharmagpt.recent_items";
  const MAX_ITEMS = 20;

  function readStore() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  function writeStore(items) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS)));
  }

  function record(type, id, title, meta, action) {
    if (!type || id == null) return;
    const items = readStore().filter(i => !(i.type === type && String(i.id) === String(id)));
    items.unshift({ type: type, id: id, title: title || "Untitled", meta: meta || "", action: action, viewedAt: new Date().toISOString() });
    writeStore(items);
  }

  function recordOpened(type, id, title, meta) { record(type, id, title, meta, "opened"); }
  function recordEdited(type, id, title, meta) { record(type, id, title, meta, "edited"); }

  function getRecent(limit, action) {
    let items = readStore();
    if (action) items = items.filter(i => i.action === action);
    return items.slice(0, limit || MAX_ITEMS);
  }

  window.PharmaRecent = { recordOpened, recordEdited, getRecent };
})();
