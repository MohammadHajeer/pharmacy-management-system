document.addEventListener("DOMContentLoaded", () => {
  const index = document.querySelector("[data-settings-index]");
  if (!index) return;

  const entries = Array.from(index.querySelectorAll('a[href^="#"]'))
    .map((link) => ({ link, section: document.getElementById(link.hash.slice(1)) }))
    .filter(({ section }) => section);
  if (!entries.length) return;

  const setCurrent = (current) => {
    entries.forEach(({ link }) => {
      if (link === current.link) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
  };

  // Five sections only: sample their positions once per frame while scrolling.
  // Use the template's scroll margin so headings clear the shared sticky topbar.
  const update = () => {
    const offset = parseFloat(getComputedStyle(entries[0].section).scrollMarginTop) || 0;
    let current = entries[0];
    entries.forEach((entry) => {
      if (entry.section.getBoundingClientRect().top <= offset + 1) current = entry;
    });
    if (window.scrollY > 0 && window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
      current = entries[entries.length - 1];
    }
    setCurrent(current);
  };

  let scheduled = false;
  const scheduleUpdate = () => {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      update();
    });
  };

  const updateFromHash = () => {
    const current = entries.find(({ link }) => link.hash === window.location.hash);
    if (current) setCurrent(current);
    else update();
  };

  // Native anchors retain focus, URL history, and keyboard behavior.
  window.addEventListener("hashchange", updateFromHash);
  window.addEventListener("scroll", scheduleUpdate, { passive: true });
  window.addEventListener("resize", scheduleUpdate);
  window.addEventListener("pageshow", updateFromHash);
  updateFromHash();
});
