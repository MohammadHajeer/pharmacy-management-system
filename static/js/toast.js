document.addEventListener("DOMContentLoaded", () => {
  const viewport = document.querySelector("#toast-viewport");
  if (!viewport) return;

  const ICONS = {
    success:
      '<path d="m5 12 4.5 4.5L19 7" stroke-linecap="round" stroke-linejoin="round" />',
    error:
      '<path d="m8 8 8 8M16 8l-8 8" stroke-linecap="round" stroke-linejoin="round" />',
    warning:
      '<path d="M12 3.5 21 20H3L12 3.5Z" stroke-linejoin="round" /><path d="M12 10v4M12 17h.01" stroke-linecap="round" />',
    info: '<circle cx="12" cy="12" r="9" /><path d="M12 11v5.5M12 8h.01" stroke-linecap="round" />',
  };
  const LEVELS = new Set(["success", "error", "warning", "info"]);

  const DURATION = 4000;
  const GAP = 10;
  const MAX_PEEK = 3;
  const MAX_TOASTS = 5;
  const SCALE_STEP = 0.05;
  const OFFSET_STEP = 12;
  const SWIPE_THRESHOLD = 80;

  const timers = new Map();

  const startTimer = (toast, duration) => {
    if (!duration || duration === Infinity) return;
    timers.set(toast, {
      remaining: duration,
      start: Date.now(),
      id: window.setTimeout(() => dismiss(toast), duration),
    });
  };
  const pauseTimer = (toast) => {
    const r = timers.get(toast);
    if (!r?.id) return;
    window.clearTimeout(r.id);
    r.remaining -= Date.now() - r.start;
    r.id = null;
  };
  const resumeTimer = (toast) => {
    const r = timers.get(toast);
    if (!r || r.id || r.remaining == null) return;
    r.start = Date.now();
    r.id = window.setTimeout(() => dismiss(toast), Math.max(r.remaining, 0));
  };
  const pauseAll = () =>
    viewport.querySelectorAll(".app-toast").forEach(pauseTimer);
  const resumeAll = () =>
    viewport.querySelectorAll(".app-toast").forEach(resumeTimer);

  const layout = () => {
    const expanded = viewport.dataset.expanded === "true";
    const stack = Array.from(
      viewport.querySelectorAll('.app-toast:not([data-closing="true"])'),
    ).reverse();

    let cumulative = 0;
    stack.forEach((toast, index) => {
      toast.style.zIndex = String(stack.length - index);
      if (expanded) {
        toast.style.transform = `translateY(-${cumulative}px) scale(1)`;
        toast.style.opacity = "1";
        toast.style.pointerEvents = "auto";
        cumulative += toast.offsetHeight + GAP;
      } else {
        const depth = Math.min(index, MAX_PEEK - 1);
        toast.style.transform = `translateY(-${depth * OFFSET_STEP}px) scale(${1 - depth * SCALE_STEP})`;
        toast.style.opacity = index < MAX_PEEK ? String(1 - index * 0.12) : "0";
        toast.style.pointerEvents = index === 0 ? "auto" : "none";
      }
    });

    const frontHeight = stack[0]?.offsetHeight ?? 0;
    const peekCount = Math.min(stack.length, MAX_PEEK);
    viewport.style.height = expanded
      ? `${Math.max(cumulative - GAP, 0)}px`
      : `${peekCount ? frontHeight + (peekCount - 1) * OFFSET_STEP : 0}px`;
  };

  const dismiss = (toast) => {
    if (!toast || toast.dataset.closing === "true") return;
    toast.dataset.closing = "true";
    const r = timers.get(toast);
    if (r?.id) window.clearTimeout(r.id);
    timers.delete(toast);

    const dragged = Number(toast.dataset.dragX || 0);
    const flyDistance =
      dragged !== 0
        ? dragged > 0
          ? window.innerWidth
          : -window.innerWidth
        : 24;
    toast.style.transform = `translateX(${flyDistance}px) scale(0.96)`;
    toast.style.opacity = "0";
    toast.style.pointerEvents = "none";

    layout();
    window.setTimeout(() => {
      toast.remove();
      layout();
    }, 400);
  };

  const attachSwipe = (toast) => {
    let startX = 0,
      dx = 0,
      dragging = false;

    toast.addEventListener("pointerdown", (e) => {
      if (e.button !== undefined && e.button !== 0) return;
      dragging = true;
      startX = e.clientX;
      toast.dataset.dragging = "true";
      toast.setPointerCapture(e.pointerId);
      pauseTimer(toast);
    });

    toast.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      dx = e.clientX - startX;
      toast.dataset.dragX = String(dx);
      const damped = dx * (1 - Math.min(Math.abs(dx) / 800, 0.4));
      toast.style.transform = `translateX(${damped}px)`;
      toast.style.opacity = String(Math.max(1 - Math.abs(dx) / 300, 0.3));
    });

    const endDrag = () => {
      if (!dragging) return;
      dragging = false;
      delete toast.dataset.dragging;
      if (Math.abs(dx) > SWIPE_THRESHOLD) {
        dismiss(toast);
      } else {
        toast.style.transform = "";
        toast.style.opacity = "";
        layout();
        resumeTimer(toast);
      }
      dx = 0;
    };

    toast.addEventListener("pointerup", endDrag);
    toast.addEventListener("pointercancel", endDrag);
  };

  const showToast = (message, requestedLevel = "info", options = {}) => {
    const text = String(message || "").trim();
    if (!text) return;

    const level = LEVELS.has(requestedLevel) ? requestedLevel : "info";
    const duration = options.duration ?? DURATION;

    const existing = viewport.querySelectorAll(
      ".app-toast:not([data-closing='true'])",
    );
    if (existing.length >= MAX_TOASTS) dismiss(existing[0]);

    const toast = document.createElement("div");
    toast.className = "app-toast";
    toast.dataset.level = level;
    toast.setAttribute("role", level === "error" ? "alert" : "status");
    toast.setAttribute("aria-atomic", "true");
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px) scale(0.96)";

    const icon = document.createElement("span");
    icon.className =
      "app-toast__icon mt-0.5 flex size-5 shrink-0 items-center justify-center";
    icon.innerHTML = `<svg class="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true">${ICONS[level]}</svg>`;

    const content = document.createElement("div");
    content.className = "min-w-0 flex-1 pt-0.5";

    const title = document.createElement("p");
    title.className = "text-sm font-medium leading-5 text-slate-900";
    title.textContent = options.title || text;
    content.append(title);

    if (options.title && text) {
      const desc = document.createElement("p");
      desc.className = "mt-1 text-sm leading-5 text-slate-500";
      desc.textContent = text;
      content.append(desc);
    }

    const close = document.createElement("button");
    close.type = "button";
    close.className =
      "absolute right-2.5 top-2.5 inline-flex size-7 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-1";
    close.setAttribute("aria-label", "Dismiss notification");
    close.innerHTML =
      '<svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" stroke-linecap="round" /></svg>';
    close.addEventListener("click", (e) => {
      e.stopPropagation();
      dismiss(toast);
    });

    toast.append(icon, content, close);
    attachSwipe(toast);
    viewport.append(toast);

    requestAnimationFrame(layout);
    startTimer(toast, duration);
  };

  const expand = () => {
    viewport.dataset.expanded = "true";
    pauseAll();
    layout();
  };
  const collapse = () => {
    delete viewport.dataset.expanded;
    resumeAll();
    layout();
  };

  viewport.addEventListener("mouseenter", expand);
  viewport.addEventListener("mouseleave", collapse);
  viewport.addEventListener("focusin", expand);
  viewport.addEventListener("focusout", (e) => {
    if (!viewport.contains(e.relatedTarget)) collapse();
  });

  window.showToast = showToast;

  document
    .querySelectorAll("#django-message-queue [data-toast-message]")
    .forEach((message) => {
      showToast(message.dataset.toastMessage, message.dataset.toastLevel, {
        title: message.dataset.toastTitle,
        duration: message.dataset.toastDuration
          ? Number(message.dataset.toastDuration)
          : undefined,
      });
    });

  document.querySelectorAll("[data-toast-trigger]").forEach((button) => {
    button.addEventListener("click", () =>
      showToast(button.dataset.toastMessage, button.dataset.toastLevel, {
        title: button.dataset.toastTitle,
        duration: button.dataset.toastDuration
          ? Number(button.dataset.toastDuration)
          : undefined,
      }),
    );
  });
});
