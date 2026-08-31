document.addEventListener("DOMContentLoaded", () => {
  const focusKey = "pharmanex.registry-search-focus";

  document.querySelectorAll("[data-registry-filter-form]").forEach((form) => {
    const search = form.querySelector('input[type="search"]');
    let timer;
    let composing = false;

    // Continue typing after the GET navigation without adding URL-only UI state.
    try {
      const saved = JSON.parse(sessionStorage.getItem(focusKey) || "null");
      sessionStorage.removeItem(focusKey);
      if (search && saved?.url === window.location.href) {
        search.focus({ preventScroll: true });
        search.setSelectionRange(saved.start, saved.end);
      }
    } catch {
      // Filtering still works when browser storage is unavailable.
    }

    const applyFilters = () => {
      clearTimeout(timer);
      const url = new URL(window.location.href);
      const data = new FormData(form);

      // Replace only this form's criteria, retaining unrelated URL parameters.
      for (const name of new Set(data.keys())) {
        url.searchParams.delete(name);
        for (const rawValue of data.getAll(name)) {
          const value = name === search?.name ? rawValue.trim() : rawValue;
          if (value !== "") url.searchParams.append(name, value);
        }
      }

      if (url.href === window.location.href) return;

      try {
        sessionStorage.removeItem(focusKey);
        if (search && document.activeElement === search) {
          sessionStorage.setItem(focusKey, JSON.stringify({
            url: url.href,
            start: search.selectionStart,
            end: search.selectionEnd,
          }));
        }
      } catch {
        // Focus restoration is optional; the server remains authoritative.
      }
      window.location.assign(url.href);
    };

    const scheduleSearch = () => {
      clearTimeout(timer);
      if (!composing) timer = setTimeout(applyFilters, 350);
    };

    search?.addEventListener("input", scheduleSearch);
    search?.addEventListener("compositionstart", () => {
      composing = true;
      clearTimeout(timer);
    });
    search?.addEventListener("compositionend", () => {
      composing = false;
      scheduleSearch();
    });
    search?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.isComposing && !composing) {
        event.preventDefault();
        applyFilters();
      }
    });

    // The shared custom select updates its native select and bubbles change.
    form.addEventListener("change", (event) => {
      if (event.target.matches("select")) applyFilters();
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!composing) applyFilters();
    });
    window.addEventListener("pagehide", () => clearTimeout(timer));
  });
});
