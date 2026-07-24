/**
 * static/js/auth.js — Supabase Auth-backed login UI and session management.
 * IMPLEMENTATION_ROADMAP.md Phase 2 step 2.6.
 *
 * Talks only to the Flask endpoints already built in routes/auth.py
 * (POST /auth/login, POST /auth/logout, GET /auth/me) — never to Supabase
 * directly, and never sees a password beyond forwarding it to /auth/login.
 *
 * Loads before every other module (see templates/index.html) so its
 * window.fetch patch is active before any business-logic module's
 * DOMContentLoaded handler can issue a request — this is how every
 * existing fetch("/...") call in dashboard.js, projects.js, etc. gets the
 * bearer token attached without a single change to those files.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "pharmagpt.session";
  const nativeFetch = window.fetch.bind(window);

  function readStoredSession() {
    const raw = localStorage.getItem(STORAGE_KEY) || sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (err) {
      return null;
    }
  }

  function writeStoredSession(session, remember) {
    const raw = JSON.stringify(session);
    if (remember) {
      localStorage.setItem(STORAGE_KEY, raw);
      sessionStorage.removeItem(STORAGE_KEY);
    } else {
      sessionStorage.setItem(STORAGE_KEY, raw);
      localStorage.removeItem(STORAGE_KEY);
    }
  }

  function clearStoredSession() {
    localStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(STORAGE_KEY);
  }

  let session = readStoredSession();

  // ── Shared toast (Phase 3.5, Objective 8 — "clear feedback") ─────────────
  // Generalizes risk.js's showToast() (the simplest of two independent,
  // per-module toast implementations already in this codebase — report.js
  // has its own '.report-toast'; neither is touched here) into one shared,
  // global function, so every module can surface a message without
  // reinventing its own toast DOM/CSS. Exposed as window.PharmaAuth.showToast.
  function showGlobalToast(message) {
    const toast = document.createElement("div");
    toast.style.cssText = `position:fixed;bottom:24px;right:24px;background:#3F3A36;color:#FFF;
      padding:12px 20px;border-radius:10px;font-size:13px;z-index:9999;max-width:360px;
      box-shadow:0 4px 20px rgba(0,0,0,0.3)`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  // ── Public API (used by static/js/*.js modules that want it, e.g. a
  // future "logged in as" display; nothing else currently depends on it) ──
  window.PharmaAuth = {
    isAuthenticated: () => !!(session && session.access_token),
    getUser: () => (session && session.user) || null,
    getAccessToken: () => (session && session.access_token) || null,
    logout: () => logout(),
    showToast: showGlobalToast,
  };

  // ── fetch() patch: attach the bearer token to same-origin requests, and
  // surface a visible toast on any 403 — the acceptance test found several
  // actions (e.g. Super Admin creating a project) failed with a correct
  // backend 403 but zero user-facing feedback; this closes that gap
  // globally, at the one chokepoint every module's fetch() already passes
  // through, without touching any individual module's own error handling. ──
  window.fetch = function (input, init) {
    const token = session && session.access_token;
    if (!token) return nativeFetch(input, init);

    const url = typeof input === "string" ? input : input.url;
    const isRelative = !/^https?:\/\//i.test(url);
    const isSameOrigin = isRelative || url.indexOf(window.location.origin) === 0;
    if (!isSameOrigin) return nativeFetch(input, init);

    const headers = new Headers(init && init.headers ? init.headers : (input && input.headers) || undefined);
    if (!headers.has("Authorization")) {
      headers.set("Authorization", "Bearer " + token);
    }
    return nativeFetch(input, Object.assign({}, init, { headers: headers })).then(function (res) {
      if (res.status === 403) {
        res
          .clone()
          .json()
          .then(function (body) {
            showGlobalToast((body && body.error) || "You don't have permission to do that.");
          })
          .catch(function () {
            showGlobalToast("You don't have permission to do that.");
          });
      }
      return res;
    });
  };

  // ── View toggling ─────────────────────────────────────────────────────
  function el(id) {
    return document.getElementById(id);
  }

  function showLogin() {
    el("login-view").style.display = "flex";
    el("session-check-view").style.display = "none";
    document.querySelector("header").style.display = "none";
    document.querySelector(".app-body").style.display = "none";
    hideUserBadge();
  }

  function showChecking() {
    el("login-view").style.display = "none";
    el("session-check-view").style.display = "flex";
    document.querySelector("header").style.display = "none";
    document.querySelector(".app-body").style.display = "none";
  }

  function showApp(user) {
    el("login-view").style.display = "none";
    el("session-check-view").style.display = "none";
    document.querySelector("header").style.display = "flex";
    document.querySelector(".app-body").style.display = "flex";
    showUserBadge(user);
    // Phase 3.5: role-gated Administration nav + Assume Company Context
    // button/banner. Defined in static/js/admin_assume_context.js, which
    // loads after this file — safe to call here because showApp() only
    // ever runs from an async continuation (after the /auth/login or
    // /auth/me fetch resolves), by which point every <script> tag below
    // this one has already executed synchronously.
    if (window.applyRoleBasedVisibility) window.applyRoleBasedVisibility(user);
  }

  function showUserBadge(user) {
    const badge = el("user-badge");
    const name = el("user-badge-name");
    if (!badge) return;
    if (name) name.textContent = (user && (user.display_name || user.email)) || "";
    badge.style.display = "flex";
    if (window.refreshIcons) window.refreshIcons();
  }

  function hideUserBadge() {
    const badge = el("user-badge");
    if (badge) badge.style.display = "none";
  }

  // ── Login form ───────────────────────────────────────────────────────
  function setSubmitting(submitting) {
    const btn = el("login-submit");
    const label = el("login-submit-label");
    const spinner = el("login-spinner");
    if (btn) btn.disabled = submitting;
    if (label) label.textContent = submitting ? "Logging in…" : "Log In";
    if (spinner) spinner.style.display = submitting ? "inline-block" : "none";
  }

  function showError(message) {
    const box = el("login-error");
    if (!box) return;
    box.textContent = message || "";
    box.style.display = message ? "block" : "none";
  }

  async function handleLoginSubmit(evt) {
    evt.preventDefault();
    showError("");

    const email = el("login-email").value.trim();
    const password = el("login-password").value;
    const remember = el("login-remember").checked;

    if (!email || !password) {
      showError("Enter both your email and password.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await nativeFetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email, password: password }),
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        showError(data.error || "Invalid email or password.");
        return;
      }

      session = {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        expires_at: data.expires_at,
        user: data.user,
      };
      writeStoredSession(session, remember);
      el("login-form").reset();
      showApp(session.user);
      // These modules' own DOMContentLoaded handlers already fired (with no
      // token) before login completed, so re-trigger them now that the
      // bearer token is in place — otherwise the sidebar Projects list (and
      // dashboard stats) would stay on their pre-login "failed to load"
      // state until the next full page refresh.
      if (window.loadDashboard) window.loadDashboard();
      if (window.loadProjects) window.loadProjects();
    } catch (err) {
      showError("Could not reach the server. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function logout() {
    try {
      await window.fetch("/auth/logout", { method: "POST" });
    } catch (err) {
      // Best-effort — the local session is cleared regardless of whether
      // the server-side revocation call succeeds.
    }
    session = null;
    clearStoredSession();
    showLogin();
  }

  // ── Boot: decide login vs. dashboard before anything else runs ─────────
  async function boot() {
    if (!session || !session.access_token) {
      showLogin();
      return;
    }

    showChecking();
    try {
      const res = await window.fetch("/auth/me");
      if (!res.ok) throw new Error("Session invalid");
      const user = await res.json();
      session.user = user;
      showApp(user);
    } catch (err) {
      session = null;
      clearStoredSession();
      showLogin();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = el("login-form");
    if (form) form.addEventListener("submit", handleLoginSubmit);

    const logoutBtn = el("btn-logout");
    if (logoutBtn) logoutBtn.addEventListener("click", logout);
  });

  boot();
})();
