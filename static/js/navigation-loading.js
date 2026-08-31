document.addEventListener("DOMContentLoaded", () => {
  const workspace = document.querySelector("[data-navigation-workspace]");
  if (!workspace) return;

  const root = document.documentElement;
  const excluded = '[data-navigation-loading="off"], [aria-disabled="true"], [disabled], [data-modal-open], [data-modal-close], [aria-haspopup="dialog"], [role="button"]';
  let pending = null;
  let safetyTimer;

  const reset = () => {
    clearTimeout(safetyTimer);
    pending = null;
    root.removeAttribute("data-navigation-pending");
    workspace.removeAttribute("aria-busy");
    document.dispatchEvent(new CustomEvent("pharmanex:navigation-reset"));
  };

  const internalURL = (href) => {
    try {
      const url = new URL(href, document.baseURI);
      return ["http:", "https:"].includes(url.protocol)
        && url.origin === window.location.origin ? url : null;
    } catch {
      return null;
    }
  };

  const sameDocument = (url) => {
    const current = new URL(window.location.href);
    return url.pathname === current.pathname && url.search === current.search;
  };

  const currentTarget = (target) => {
    const effective = target ?? document.querySelector("base[target]")?.getAttribute("target") ?? "";
    return effective === "" || effective.toLowerCase() === "_self";
  };

  const navigationLink = (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return null;
    const link = event.target.closest?.("a[href]");
    if (!link || link.closest(excluded) || link.hasAttribute("download")
      || !currentTarget(link.getAttribute("target"))) return null;
    const href = link.getAttribute("href").trim();
    if (!href || href.startsWith("#")) return null;
    const url = internalURL(href);
    // Same-page anchors (including absolute URLs) do not load another document.
    if (!url || (sameDocument(url) && (url.hash || url.href === window.location.href))) return null;
    return link;
  };

  const navigationForm = (event) => {
    const form = event.target;
    const submitter = event.submitter;
    if (!form.matches?.("form") || form.closest('[data-navigation-loading="off"]')
      || submitter?.closest('[data-navigation-loading="off"]')) return false;
    const method = submitter?.getAttribute("formmethod") ?? form.getAttribute("method") ?? "get";
    const target = submitter?.getAttribute("formtarget") ?? form.getAttribute("target");
    const action = submitter?.getAttribute("formaction") ?? form.getAttribute("action");
    return method.toLowerCase() !== "dialog" && currentTarget(target)
      && !!internalURL(action || window.location.href);
  };

  const begin = (event) => {
    if (event.defaultPrevented) return;
    if (pending) {
      event.preventDefault();
      return;
    }
    pending = event;
    root.setAttribute("data-navigation-pending", "true");
    workspace.setAttribute("aria-busy", "true");
    // No unload listener: keep BFCache available. This also covers Stop,
    // downloads returned by the server, and a canceled beforeunload prompt.
    safetyTimer = setTimeout(reset, 15000);
    // A later listener can still cancel this event. Check after dispatch,
    // without preventing, replaying, or delaying the browser's default action.
    setTimeout(() => {
      if (pending === event && event.defaultPrevented) reset();
    }, 0);
  };

  // Capture only blocks a second navigation, before local submit/filter handlers
  // run. The first event bubbles normally so local cancellation takes priority.
  window.addEventListener("click", (event) => {
    if (pending && navigationLink(event)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  window.addEventListener("submit", (event) => {
    if (pending && navigationForm(event)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  window.addEventListener("click", (event) => {
    if (navigationLink(event)) begin(event);
  });
  // Native validation happens before submit; invalid forms never reach here.
  window.addEventListener("submit", (event) => {
    if (navigationForm(event)) begin(event);
  });

  // Registry filters keep ownership of URL construction and location.assign.
  document.addEventListener("pharmanex:before-navigate", (event) => {
    const url = internalURL(event.detail?.url);
    if (url && !sameDocument(url)) begin(event);
  });
  window.addEventListener("pageshow", reset);
  reset();
});
