document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.querySelector("#dashboard-sidebar");
  const backdrop = document.querySelector("#sidebar-backdrop");
  const openButton = document.querySelector("[data-sidebar-open]");
  const closeButton = document.querySelector("[data-sidebar-close]");
  const accountMenu = sidebar?.querySelector("[data-sidebar-account-menu]");
  const accountTrigger = sidebar?.querySelector("[data-sidebar-account-trigger]");

  if (!sidebar || !backdrop || !openButton) return;

  const setAccountExpanded = (expanded) => {
    accountTrigger?.setAttribute("aria-expanded", expanded ? "true" : "false");
  };

  const closeAccountMenu = ({ restoreFocus = false } = {}) => {
    if (!accountMenu?.open) return false;
    accountMenu.open = false;
    setAccountExpanded(false);
    if (restoreFocus) accountTrigger?.focus();
    return true;
  };

  const openSidebar = () => {
    sidebar.classList.remove("-translate-x-full");
    sidebar.classList.add("translate-x-0");
    backdrop.classList.remove("hidden");
    openButton.setAttribute("aria-expanded", "true");
    document.body.classList.add("overflow-hidden");
    closeButton?.focus();
  };

  const closeSidebar = ({ restoreFocus = true } = {}) => {
    closeAccountMenu();
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

  accountMenu?.addEventListener("toggle", () => {
    setAccountExpanded(accountMenu.open);
  });

  accountMenu?.querySelectorAll("[data-modal-open]").forEach((button) => {
    button.addEventListener("click", () => {
      closeAccountMenu({ restoreFocus: true });
      if (openButton.getAttribute("aria-expanded") === "true") closeSidebar();
    });
  });

  document.addEventListener("click", (event) => {
    if (accountMenu?.open && !accountMenu.contains(event.target)) {
      closeAccountMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && closeAccountMenu({ restoreFocus: true })) return;
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
