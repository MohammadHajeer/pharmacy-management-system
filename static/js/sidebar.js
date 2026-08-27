document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.querySelector("#dashboard-sidebar");
  const backdrop = document.querySelector("#sidebar-backdrop");
  const openButton = document.querySelector("[data-sidebar-open]");
  const closeButton = document.querySelector("[data-sidebar-close]");

  if (!sidebar || !backdrop || !openButton) return;

  const openSidebar = () => {
    sidebar.classList.remove("-translate-x-full");
    sidebar.classList.add("translate-x-0");
    backdrop.classList.remove("hidden");
    openButton.setAttribute("aria-expanded", "true");
    document.body.classList.add("overflow-hidden");
    closeButton?.focus();
  };

  const closeSidebar = ({ restoreFocus = true } = {}) => {
    sidebar.classList.add("-translate-x-full");
    sidebar.classList.remove("translate-x-0");
    backdrop.classList.add("hidden");
    openButton.setAttribute("aria-expanded", "false");
    document.body.classList.remove("overflow-hidden");
    if (restoreFocus) openButton.focus();
  };

  openButton.addEventListener("click", openSidebar);
  closeButton?.addEventListener("click", () => closeSidebar());
  backdrop.addEventListener("click", () => closeSidebar());

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && openButton.getAttribute("aria-expanded") === "true") {
      closeSidebar();
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth >= 1024 && openButton.getAttribute("aria-expanded") === "true") {
      closeSidebar({ restoreFocus: false });
    }
  });
});
