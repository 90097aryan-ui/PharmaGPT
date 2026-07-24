/**
 * static/js/favorites.js — Phase 5: browser-local Favorites (pin/unpin).
 *
 * Mirrors auth.js's storage convention exactly: one STORAGE_KEY constant,
 * JSON-serialized, small named read/write helpers, wrapped in an IIFE,
 * exposed only via window.PharmaFavorites. Browser localStorage only — no
 * backend endpoint, no server-side persistence, per spec section 6.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "pharmagpt.favorites";
  const TYPES = ["projects", "equipment", "sops", "validation_docs"];

  function readStore() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      TYPES.forEach(t => { if (!Array.isArray(parsed[t])) parsed[t] = []; });
      return parsed;
    } catch (e) {
      const empty = {};
      TYPES.forEach(t => { empty[t] = []; });
      return empty;
    }
  }

  function writeStore(store) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  }

  function isFavorite(type, id) {
    const store = readStore();
    if (!store[type]) return false;
    return store[type].some(f => String(f.id) === String(id));
  }

  function toggleFavorite(type, id, meta) {
    if (TYPES.indexOf(type) === -1) return false;
    const store = readStore();
    const list = store[type];
    const idx = list.findIndex(f => String(f.id) === String(id));
    if (idx !== -1) {
      list.splice(idx, 1);
      writeStore(store);
      return false; // now unfavorited
    }
    list.unshift(Object.assign({ id: id, savedAt: new Date().toISOString() }, meta || {}));
    writeStore(store);
    return true; // now favorited
  }

  function getFavorites(type) {
    const store = readStore();
    return type ? (store[type] || []).slice() : store;
  }

  function getAllFlat() {
    const store = readStore();
    const flat = [];
    TYPES.forEach(t => (store[t] || []).forEach(f => flat.push(Object.assign({ type: t }, f))));
    flat.sort((a, b) => (b.savedAt || "").localeCompare(a.savedAt || ""));
    return flat;
  }

  window.PharmaFavorites = { toggleFavorite, isFavorite, getFavorites, getAllFlat, TYPES };
})();
