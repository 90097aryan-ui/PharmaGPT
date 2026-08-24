/**
 * static/js/login_animation.js — decorative-only login animation layer.
 *
 * Explicitly does NOT touch authentication: it never reads #login-email or
 * #login-password values, never calls fetch, and never registers a
 * preventDefault()-ing submit handler. It only watches DOM state that
 * static/js/auth.js already sets (the spinner/error display it was already
 * toggling before this file existed) and mirrors it into `.is-active` /
 * `.is-loading` classes on #login-scene for pharmagpt/static/css/login.css
 * to animate, plus a WAAPI shake on #login-card for error feedback.
 *
 * auth.js is loaded before this file and is unmodified.
 */
(function () {
  "use strict";

  function init() {
    var scene = document.getElementById("login-scene");
    var card = document.getElementById("login-card");
    var form = document.getElementById("login-form");
    var spinner = document.getElementById("login-spinner");
    var errorBox = document.getElementById("login-error");
    if (!scene || !card || !form || !spinner || !errorBox) return;

    var reduceMotionMQ = window.matchMedia
      ? window.matchMedia("(prefers-reduced-motion: reduce)")
      : null;

    // Driven via the Web Animations API rather than a CSS class: toggling a
    // class that swaps .login-card's `animation` shorthand (its entrance
    // animation lives there) would change animation-name away and back,
    // which restarts login-card-enter underneath the shake — a visible
    // "re-fade-in" glitch on every failed attempt. A .animate() call
    // composites independently and reverts cleanly with no such
    // side-effect. Skipped outright under reduced-motion — the existing
    // role="alert" error text already conveys the failure without motion.
    function shakeCard() {
      if (reduceMotionMQ && reduceMotionMQ.matches) return;
      if (typeof card.animate !== "function") return;
      card.animate(
        [
          { transform: "translateX(0)" },
          { transform: "translateX(-4px)" },
          { transform: "translateX(4px)" },
          { transform: "translateX(-3px)" },
          { transform: "translateX(3px)" },
          { transform: "translateX(-1px)" },
          { transform: "translateX(1px)" },
          { transform: "translateX(0)" },
        ],
        { duration: 500, easing: "ease" }
      );
    }

    // Card/lamp "active" state follows real focus, via delegation — no need
    // to touch individual fields or read their values.
    form.addEventListener("focusin", function () {
      scene.classList.add("is-active");
    });
    form.addEventListener("focusout", function () {
      // Defer so a focus move between two fields inside the form doesn't
      // cause a flicker off-then-on.
      window.requestAnimationFrame(function () {
        if (!form.contains(document.activeElement)) {
          scene.classList.remove("is-active");
        }
      });
    });

    // Loading state mirrors #login-spinner's own display, which auth.js's
    // setSubmitting() already toggles — purely observational.
    var spinnerObserver = new MutationObserver(function () {
      var loading = spinner.style.display !== "none" && spinner.style.display !== "";
      scene.classList.toggle("is-loading", loading);
    });
    spinnerObserver.observe(spinner, { attributes: true, attributeFilter: ["style"] });

    // Error shake mirrors #login-error's own display, which auth.js's
    // showError() already toggles — purely observational.
    var errorObserver = new MutationObserver(function () {
      var visible = errorBox.style.display !== "none" && errorBox.textContent.trim() !== "";
      if (visible) shakeCard();
    });
    errorObserver.observe(errorBox, { attributes: true, attributeFilter: ["style"] });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
