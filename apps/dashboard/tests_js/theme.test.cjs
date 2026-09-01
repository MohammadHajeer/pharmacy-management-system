const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const rootPath = path.resolve(__dirname, "../../..");
const init = fs.readFileSync(path.join(rootPath, "templates/components/theme_init.html"), "utf8").replace(/<\/?script>/g, "");
const script = fs.readFileSync(path.join(rootPath, "static/js/theme.js"), "utf8");

function page({ saved = null, dark = false, blocked = false, media = true } = {}) {
  const listeners = {};
  const classes = new Set();
  const attributes = new Map();
  const button = { hidden: true, setAttribute(name, value) { this[name] = value; } };
  const events = [];
  let flushes = 0;
  const root = {
    dataset: {},
    setAttribute: (name, value) => attributes.set(name, value),
    removeAttribute: (name) => attributes.delete(name),
    classList: { contains: (name) => classes.has(name), toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); } },
  };
  const addEventListener = (name, fn) => { listeners[name] = fn; };
  const system = { matches: dark, addEventListener };
  const storage = {
    getItem(key) { assert.equal(key, "pharmanex.theme"); if (blocked) throw Error("denied"); return saved; },
    setItem(key, value) { assert.equal(key, "pharmanex.theme"); if (blocked) throw Error("denied"); saved = value; },
  };
  const context = vm.createContext({
    localStorage: storage,
    window: { addEventListener, ...(media ? { matchMedia: () => system } : {}) },
    document: {
      documentElement: root, querySelectorAll: () => [button], addEventListener,
      dispatchEvent(event) {
        assert.equal(attributes.has("data-theme-changing"), true);
        assert.equal(root.classList.contains("dark"), event.detail.theme === "dark");
        events.push(event);
      },
    },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    getComputedStyle: () => ({ getPropertyValue() { assert.equal(attributes.has("data-theme-changing"), true); flushes++; return ""; } }),
  });
  vm.runInContext(init, context);
  return {
    root, button, events, attributes,
    start: () => vm.runInContext(script, context),
    toggle: () => listeners.click({ target: { closest: () => button } }),
    system(value) { system.matches = value; listeners.change(); },
    restore: () => listeners.pageshow({ persisted: true }),
    storage(value, key = "pharmanex.theme") { saved = value; listeners.storage({ key }); },
    saved: () => saved, flushes: () => flushes,
  };
}

for (const [saved, system, expected] of [["light", true, false], ["dark", false, true], ["system", true, true], [null, false, false], ["invalid", true, true]]) {
  test(`head bootstrap resolves ${saved} with system=${system} before deferred code`, () => {
    const fixture = page({ saved, dark: system });
    assert.equal(fixture.root.classList.contains("dark"), expected);
    fixture.start();
    assert.equal(fixture.root.classList.contains("dark"), expected);
    assert.equal(fixture.button.hidden, false);
    assert.equal(fixture.button["aria-label"], expected ? "Switch to light mode" : "Switch to dark mode");
  });
}

test("toggle persists, updates labels and dispatches synchronously with transitions suppressed", () => {
  const fixture = page();
  fixture.start();
  fixture.toggle();
  assert.equal(fixture.saved(), "dark");
  assert.equal(fixture.root.classList.contains("dark"), true);
  assert.equal(fixture.button.title, "Switch to light mode");
  assert.equal(fixture.events[0].type, "pharmanex:theme-change");
  assert.equal(fixture.events.length, 1);
  assert.equal(fixture.attributes.has("data-theme-changing"), false);
  assert.equal(fixture.flushes(), 2);
  fixture.toggle();
  assert.equal(fixture.saved(), "light");
  assert.equal(fixture.root.classList.contains("dark"), false);
});

test("system changes apply only to system preference", () => {
  const fixture = page({ saved: "system" });
  fixture.start();
  fixture.system(true);
  assert.equal(fixture.root.classList.contains("dark"), true);
  fixture.toggle();
  fixture.system(true);
  assert.equal(fixture.root.classList.contains("dark"), false);
});

test("storage and pageshow restore saved state without navigation or duplicate events", () => {
  const fixture = page();
  fixture.start();
  fixture.storage("dark");
  fixture.restore();
  assert.equal(fixture.root.classList.contains("dark"), true);
  assert.equal(fixture.events.length, 1);
  fixture.storage("light", "another-key");
  assert.equal(fixture.root.classList.contains("dark"), true);
  fixture.restore();
  assert.equal(fixture.root.classList.contains("dark"), false);
  fixture.storage(null, null);
  fixture.system(true);
  assert.equal(fixture.root.classList.contains("dark"), true);
});

test("blocked storage keeps a working in-memory toggle across pageshow", () => {
  const fixture = page({ blocked: true, dark: true });
  fixture.start();
  fixture.toggle();
  fixture.restore();
  assert.equal(fixture.root.classList.contains("dark"), false);
});

test("missing matchMedia safely defaults to light", () => {
  const fixture = page({ media: false });
  fixture.start();
  assert.equal(fixture.root.classList.contains("dark"), false);
  fixture.toggle();
  assert.equal(fixture.root.classList.contains("dark"), true);
});

test("print retains light tokens and hides operational chrome without changing preference", () => {
  const css = fs.readFileSync(path.join(rootPath, "assets/css/input.css"), "utf8");
  function block(marker) {
    const start = css.indexOf("{", css.indexOf(marker));
    let depth = 1;
    let end = start + 1;
    for (; depth && end < css.length; end++) {
      if (css[end] === "{") depth++;
      if (css[end] === "}") depth--;
    }
    return css.slice(start + 1, end - 1);
  }
  assert.match(block("@media screen"), /:root\.dark/);
  assert.equal(css.match(/:root\.dark/g).length, 1);
  const print = block("@media print");
  assert.match(print, /color-scheme: light/);
  assert.match(print, /background: white !important/);
  assert.match(print, /\[data-theme-toggle\]/);
  assert.match(print, /#toast-viewport/);
  assert.match(print, /display: none !important/);
});

test("theme changes suppress all transitions while normal toast motion stays transform-only", () => {
  const css = fs.readFileSync(path.join(rootPath, "assets/css/input.css"), "utf8");
  assert.match(css, /html\[data-theme-changing\][\s\S]*?transition: none !important;\s*animation: none !important/);
  assert.match(css, /transition:\s*transform [^;]+opacity [^;]+;/);
  for (const file of ["input", "textarea", "select", "button", "topbar", "modal"]) {
    const template = fs.readFileSync(path.join(rootPath, `templates/components/${file}.html`), "utf8");
    assert.doesNotMatch(template, /transition-(colors|all)/);
  }
});

test("dashboard chrome uses theme-specific sidebar roles with branded navigation state", () => {
  const css = fs.readFileSync(path.join(rootPath, "assets/css/input.css"), "utf8");
  const sidebar = fs.readFileSync(path.join(rootPath, "templates/components/sidebar.html"), "utf8");
  const topbar = fs.readFileSync(path.join(rootPath, "templates/components/topbar.html"), "utf8");

  assert.match(css, /--color-shell-sidebar: #076b64/);
  assert.match(css, /--color-sidebar-active: #0b8278/);
  assert.match(css, /--color-shell-sidebar: #081518/);
  assert.match(css, /--color-sidebar-active: color-mix/);
  assert.match(sidebar, /bg-shell-sidebar/);
  assert.match(sidebar, /class="flex h-16 shrink-0/);
  assert.match(sidebar, /src="{% static 'logo-white\.png' %}"/);
  assert.doesNotMatch(sidebar, /src="{% static 'logo\.png' %}"/);
  assert.match(sidebar, /aria-current="page"/);
  assert.match(sidebar, /before:bg-sidebar-accent/);
  assert.match(sidebar, /hover:bg-sidebar-hover/);
  assert.match(sidebar, /focus-visible:ring-sidebar-focus/);
  assert.match(sidebar, /data-sidebar-account-footer/);
  assert.match(sidebar, /bottom-full/);
  assert.match(sidebar, /role="menu" aria-label="Account menu"/);
  assert.match(sidebar, /id="sidebar-account-popover" class="[^"]*border border-line bg-surface/);
  assert.match(sidebar, /text-accent">Signed in as/);
  assert.match(sidebar, /class="[^"]*text-ink hover:bg-surface-hover[^"]*"[^>]*role="menuitem"/);
  assert.doesNotMatch(sidebar, /id="sidebar-account-popover" class="[^"]*bg-shell-sidebar/);
  assert.doesNotMatch(topbar, /data-account-identity/);
  assert.doesNotMatch(sidebar, /bg-sidebar-900|bg-sidebar-800/);
  assert.match(topbar, /bg-shell-topbar\/95/);
});
