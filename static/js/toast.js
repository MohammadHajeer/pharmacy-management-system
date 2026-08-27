document.addEventListener("DOMContentLoaded", () => {
  const viewport = document.querySelector("#toast-viewport");
  if (!viewport) return;

  const icons = {
    success: '<path d="m7 12 3 3 7-7" stroke-linecap="round" stroke-linejoin="round" />',
    error: '<path d="M12 8v4M12 16h.01" stroke-linecap="round" />',
    warning: '<path d="M12 8v4M12 16h.01" stroke-linecap="round" />',
    info: '<path d="M12 11v5M12 8h.01" stroke-linecap="round" />',
  };
  const titles = { success: "Success", error: "Error", warning: "Warning", info: "Information" };

  const dismiss = (toast) => {
    if (!toast || toast.dataset.closing === "true") return;
    toast.dataset.closing = "true";
    window.setTimeout(() => toast.remove(), 160);
  };

  const showToast = (message, requestedLevel = "info") => {
    const level = Object.hasOwn(titles, requestedLevel) ? requestedLevel : "info";
    const toast = document.createElement("div");
    toast.className = "app-toast";
    toast.dataset.level = level;
    toast.setAttribute("role", level === "error" ? "alert" : "status");

    const icon = document.createElement("span");
    icon.className = "app-toast__icon flex size-8 shrink-0 items-center justify-center rounded-full";
    icon.innerHTML = `<svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">${icons[level]}</svg>`;

    const content = document.createElement("div");
    content.className = "min-w-0 flex-1";
    const title = document.createElement("p");
    title.className = "text-sm font-semibold text-slate-900";
    title.textContent = titles[level];
    const text = document.createElement("p");
    text.className = "mt-0.5 text-sm leading-5 text-slate-600";
    text.textContent = message;
    content.append(title, text);

    const close = document.createElement("button");
    close.type = "button";
    close.className = "absolute right-2.5 top-2.5 rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-2 focus-visible:outline-primary-600";
    close.setAttribute("aria-label", "Dismiss notification");
    close.innerHTML = '<svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" stroke-linecap="round" /></svg>';
    close.addEventListener("click", () => dismiss(toast));

    toast.append(icon, content, close);
    viewport.append(toast);
    window.setTimeout(() => dismiss(toast), 5000);
  };

  window.showToast = showToast;

  document.querySelectorAll("#django-message-queue [data-toast-message]").forEach((message) => {
    showToast(message.dataset.toastMessage, message.dataset.toastLevel);
  });

  document.querySelectorAll("[data-toast-trigger]").forEach((button) => {
    button.addEventListener("click", () => showToast(button.dataset.toastMessage, button.dataset.toastLevel));
  });
});
