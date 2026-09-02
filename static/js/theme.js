(() => {
  "use strict";

  const root = document.documentElement;
  const key = "pharmanex.theme";
  const system = window.matchMedia?.("(prefers-color-scheme: dark)");
  const normalize = (value) => ["light", "dark", "system"].includes(value) ? value : "system";
  let preference = normalize(root.dataset.themePreference);

  function apply(value) {
    preference = normalize(value);
    const dark = preference === "dark" || (preference === "system" && Boolean(system?.matches));
    const changed = root.classList.contains("dark") !== dark;
    root.setAttribute("data-theme-changing", "");
    root.classList.toggle("dark", dark);
    root.dataset.themePreference = preference;
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      const label = dark ? "Switch to light mode" : "Switch to dark mode";
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
      button.setAttribute("aria-checked", String(dark));
      button.hidden = false;
    });
    if (changed) {
      document.dispatchEvent(new CustomEvent("pharmanex:theme-change", {
        detail: { theme: dark ? "dark" : "light", preference },
      }));
    }
    // Resolve the new colors while transitions are disabled, before paint.
    getComputedStyle(root).getPropertyValue("color-scheme");
    root.removeAttribute("data-theme-changing");
  }

  function restore() {
    let saved = preference;
    try { saved = localStorage.getItem(key); } catch (_) {}
    apply(saved);
  }

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-theme-toggle]")) return;
    const next = root.classList.contains("dark") ? "light" : "dark";
    try { localStorage.setItem(key, next); } catch (_) {}
    apply(next);
  });
  system?.addEventListener("change", () => {
    if (preference === "system") apply(preference);
  });
  window.addEventListener("storage", (event) => {
    if (event.key === key || event.key === null) restore();
  });
  window.addEventListener("pageshow", restore);
  restore();
})();
