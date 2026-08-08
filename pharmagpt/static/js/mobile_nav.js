// mobile_nav.js — additive mobile shell controller.
// Owns only: hamburger drawer open/close, backdrop/Escape-to-close, and
// bottom-tab-bar clicks. Every bottom-nav button just re-clicks the real,
// existing sidebar item it mirrors (#nav-dashboard, #nav-kb, ...) — same
// "simulate a click on the element that already owns the view switch"
// pattern the Workspace Selector cards use. No new view-switching logic,
// no new fetches, no route changes.
(function () {
  function sidebarEl()   { return document.querySelector(".sidebar"); }
  function backdropEl()  { return document.getElementById("sidebar-backdrop"); }

  function openDrawer() {
    if (sidebarEl())  sidebarEl().classList.add("mobile-open");
    document.body.classList.add("mobile-nav-drawer-open");
    var btn = document.getElementById("mobile-menu-btn");
    if (btn) btn.setAttribute("aria-expanded", "true");
  }
  function closeDrawer() {
    if (sidebarEl())  sidebarEl().classList.remove("mobile-open");
    document.body.classList.remove("mobile-nav-drawer-open");
    var btn = document.getElementById("mobile-menu-btn");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }
  function toggleDrawer() {
    if (sidebarEl() && sidebarEl().classList.contains("mobile-open")) closeDrawer();
    else openDrawer();
  }

  function syncBottomNavActive() {
    var visible = null;
    document.querySelectorAll("main[id^='view-']").forEach(function (v) {
      if (!visible && getComputedStyle(v).display !== "none") visible = v.id;
    });
    document.querySelectorAll(".bottom-nav-item[data-target]").forEach(function (btn) {
      var targetEl = document.getElementById(btn.dataset.target);
      var viewId = targetEl ? targetEl.dataset.view : null;
      btn.classList.toggle("active", !!viewId && viewId === visible);
    });
  }

  function syncChromeVisibility() {
    var header = document.querySelector("header");
    var visible = header && getComputedStyle(header).display !== "none";
    document.body.classList.toggle("mobile-chrome-visible", !!visible);
    if (!visible) closeDrawer();
  }

  document.addEventListener("DOMContentLoaded", function () {
    var hamburger = document.getElementById("mobile-menu-btn");
    var backdrop  = backdropEl();

    if (hamburger) hamburger.addEventListener("click", toggleDrawer);
    if (backdrop)  backdrop.addEventListener("click", closeDrawer);

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawer();
    });

    // Any real navigation inside the drawer should close it behind itself.
    document.querySelectorAll(".sidebar-item").forEach(function (item) {
      item.addEventListener("click", closeDrawer);
    });

    document.querySelectorAll(".bottom-nav-item[data-target]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = document.getElementById(btn.dataset.target);
        if (target) target.click();
        closeDrawer();
      });
    });

    document.querySelectorAll("main[id^='view-']").forEach(function (v) {
      new MutationObserver(syncBottomNavActive)
        .observe(v, { attributes: true, attributeFilter: ["style"] });
    });
    syncBottomNavActive();

    var header = document.querySelector("header");
    if (header) {
      new MutationObserver(syncChromeVisibility)
        .observe(header, { attributes: true, attributeFilter: ["style"] });
    }
    syncChromeVisibility();
  });
})();
