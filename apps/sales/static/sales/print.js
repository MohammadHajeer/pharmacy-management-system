document.addEventListener("DOMContentLoaded", () => {
  document.querySelector("[data-print-button] button")?.addEventListener("click", () => window.print());
});
