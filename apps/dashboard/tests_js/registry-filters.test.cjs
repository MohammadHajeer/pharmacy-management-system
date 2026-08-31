const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const script = readFileSync(resolve(__dirname, "../../../static/js/registry-filters.js"), "utf8");

function setup(href, { hasSearch = true, storageBlocked = false } = {}) {
  const listeners = (target) => Object.assign(target, {
    handlers: {},
    addEventListener(type, handler) {
      (this.handlers[type] ||= []).push(handler);
    },
    emit(type, properties = {}) {
      const event = { target: this, preventDefault() {}, ...properties };
      for (const handler of this.handlers[type] || []) handler(event);
    },
  });
  const query = new URL(href).searchParams;
  const search = hasSearch ? listeners({ name: "q", value: query.get("q") || "", selectionStart: 0, selectionEnd: 0 }) : null;
  const select = { name: "status", value: query.get("status") || "active", matches: (selector) => selector === "select" };
  const form = listeners({
    querySelector: () => search,
    reset() {
      if (search) search.value = query.get("q") || "";
      select.value = query.get("status") || "active";
    },
  });
  const document = listeners({ querySelectorAll: () => [form], activeElement: null });
  if (search) {
    search.focus = () => { document.activeElement = search; };
    search.setSelectionRange = (start, end) => { search.selectionStart = start; search.selectionEnd = end; };
  }
  const navigations = [];
  const window = listeners({ location: { href, assign: (url) => navigations.push(new URL(url)) } });
  const storage = new Map();
  const sessionStorage = {
    getItem(key) { if (storageBlocked) throw Error("Storage unavailable"); return storage.get(key); },
    setItem(key, value) { if (storageBlocked) throw Error("Storage unavailable"); storage.set(key, value); },
    removeItem(key) { storage.delete(key); },
  };
  let now = 0;
  let sequence = 0;
  const timers = new Map();
  const context = vm.createContext({
    document, window, sessionStorage, URL,
    FormData: class {
      constructor() { this.entries = [search, select].filter(Boolean).map(({ name, value }) => [name, value]); }
      keys() { return this.entries.map(([name]) => name).values(); }
      getAll(name) { return this.entries.filter(([key]) => key === name).map(([, value]) => value); }
    },
    setTimeout(callback, delay) { const id = ++sequence; timers.set(id, { callback, at: now + delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
  });
  vm.runInContext(script, context);
  document.emit("DOMContentLoaded");
  return {
    search, select, form, document, window, navigations,
    advance(ms) {
      now += ms;
      for (const [id, timer] of [...timers]) if (timer.at <= now) { timers.delete(id); timer.callback(); }
    },
  };
}

test("search waits 350 ms after the last input and preserves other query parameters", () => {
  const ui = setup("https://example.test/catalog/medicines/?status=inactive&sort=name&tag=a&tag=b&page=5");
  ui.search.value = "p";
  ui.search.emit("input");
  ui.advance(200);
  ui.search.value = "panadol";
  ui.search.emit("input");
  ui.advance(349);
  assert.equal(ui.navigations.length, 0);
  ui.advance(1);
  assert.equal(ui.navigations.length, 1);
  assert.equal(ui.navigations[0].searchParams.get("q"), "panadol");
  assert.equal(ui.navigations[0].searchParams.get("status"), "inactive");
  assert.deepEqual(ui.navigations[0].searchParams.getAll("tag"), ["a", "b"]);
  assert.equal(ui.navigations[0].searchParams.get("sort"), "name");
  assert.equal(ui.navigations[0].searchParams.has("page"), false);
});

test("Enter applies immediately and cancels pending debounce", () => {
  const ui = setup("https://example.test/parties/suppliers/?page=5");
  ui.search.value = "Supply & Co";
  ui.search.emit("input");
  ui.search.emit("keydown", { key: "Enter" });
  assert.equal(ui.navigations.length, 1);
  assert.equal(ui.navigations[0].searchParams.get("q"), "Supply & Co");
  assert.equal(ui.navigations[0].searchParams.has("page"), false);
  ui.advance(500);
  assert.equal(ui.navigations.length, 1);
});

test("clearing the search removes q and preserves the selected status", () => {
  const ui = setup("https://example.test/parties/customers/?q=Sam&status=all&page=5");
  ui.search.value = "   ";
  ui.search.emit("input");
  ui.advance(350);
  assert.equal(ui.navigations[0].searchParams.has("q"), false);
  assert.equal(ui.navigations[0].searchParams.get("status"), "all");
  assert.equal(ui.navigations[0].searchParams.has("page"), false);
});

test("native select change applies pending search immediately without a second navigation", () => {
  const ui = setup("https://example.test/parties/prescribers/?q=Example&status=active&page=5");
  ui.search.value = "Dr Example";
  ui.search.emit("input");
  ui.select.value = "inactive";
  ui.form.emit("change", { target: ui.select });
  assert.equal(ui.navigations[0].searchParams.get("q"), "Dr Example");
  assert.equal(ui.navigations[0].searchParams.get("status"), "inactive");
  assert.equal(ui.navigations[0].searchParams.has("page"), false);
  ui.advance(500);
  assert.equal(ui.navigations.length, 1);
});

test("IME composition does not navigate until the text is committed", () => {
  const ui = setup("https://example.test/catalog/medicines/");
  ui.search.emit("compositionstart");
  ui.search.value = "دواء";
  ui.search.emit("input");
  ui.search.emit("keydown", { key: "Enter", isComposing: true });
  ui.advance(1000);
  assert.equal(ui.navigations.length, 0);
  ui.search.emit("compositionend");
  ui.advance(350);
  assert.equal(ui.navigations[0].searchParams.get("q"), "دواء");
});

test("unchanged filters do not reload and status-only forms work without storage", () => {
  const ui = setup("https://example.test/catalog/categories/?status=active", { hasSearch: false, storageBlocked: true });
  ui.form.emit("submit");
  assert.equal(ui.navigations.length, 0);
  ui.select.value = "all";
  ui.form.emit("change", { target: ui.select });
  assert.equal(ui.navigations[0].searchParams.get("status"), "all");
  assert.equal(ui.navigations[0].searchParams.has("q"), false);
});

test("leaving the page cancels a pending search", () => {
  const ui = setup("https://example.test/catalog/medicines/");
  ui.search.value = "Example";
  ui.search.emit("input");
  ui.window.emit("pagehide");
  ui.advance(350);
  assert.equal(ui.navigations.length, 0);
});

test("form submission removes repeated page parameters and keeps unrelated filters", () => {
  const ui = setup("https://example.test/catalog/medicines/?page=5&page=9&category=7&manufacturer=3");
  ui.search.value = "Filtered";
  ui.form.emit("submit");
  assert.equal(ui.navigations[0].searchParams.has("page"), false);
  assert.equal(ui.navigations[0].searchParams.get("category"), "7");
  assert.equal(ui.navigations[0].searchParams.get("manufacturer"), "3");
});

test("other filter selects such as sort reset the page immediately", () => {
  const ui = setup("https://example.test/catalog/medicines/?sort=name&page=5", { hasSearch: false });
  ui.select.name = "sort";
  ui.select.value = "date";
  ui.form.emit("change", { target: ui.select });
  assert.equal(ui.navigations[0].searchParams.get("sort"), "date");
  assert.equal(ui.navigations[0].searchParams.has("page"), false);
});

test("history restores server-rendered filters without navigating or losing the page", () => {
  const ui = setup("https://example.test/catalog/medicines/?q=Original&status=active&page=5");
  ui.search.value = "Later search";
  ui.select.value = "inactive";
  ui.window.emit("pageshow", { persisted: true });
  ui.advance(0);
  assert.equal(ui.search.value, "Original");
  assert.equal(ui.select.value, "active");
  assert.equal(new URL(ui.window.location.href).searchParams.get("page"), "5");
  assert.equal(ui.navigations.length, 0);
});

test("normal page display preserves search editing and caret restoration", () => {
  const ui = setup("https://example.test/catalog/medicines/?q=Original");
  ui.search.value = "Already typing";
  ui.window.emit("pageshow", { persisted: false });
  ui.advance(0);
  assert.equal(ui.search.value, "Already typing");
  assert.equal(ui.navigations.length, 0);
});

test("uncached Back navigation also restores server-rendered criteria", () => {
  const ui = setup("https://example.test/catalog/medicines/?q=Original&page=2");
  ui.window.performance = { getEntriesByType: () => [{ type: "back_forward" }] };
  ui.search.value = "Later search";
  ui.window.emit("pageshow", { persisted: false });
  ui.advance(0);
  assert.equal(ui.search.value, "Original");
  assert.equal(ui.navigations.length, 0);
});
