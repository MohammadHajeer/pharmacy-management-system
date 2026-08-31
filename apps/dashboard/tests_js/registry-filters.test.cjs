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
  const form = listeners({ querySelector: () => search });
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
  const ui = setup("https://example.test/catalog/medicines/?status=inactive&sort=name&tag=a&tag=b");
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
});

test("Enter applies immediately and cancels pending debounce", () => {
  const ui = setup("https://example.test/parties/suppliers/");
  ui.search.value = "Supply & Co";
  ui.search.emit("input");
  ui.search.emit("keydown", { key: "Enter" });
  assert.equal(ui.navigations.length, 1);
  assert.equal(ui.navigations[0].searchParams.get("q"), "Supply & Co");
  ui.advance(500);
  assert.equal(ui.navigations.length, 1);
});

test("clearing the search removes q and preserves the selected status", () => {
  const ui = setup("https://example.test/parties/customers/?q=Sam&status=all");
  ui.search.value = "   ";
  ui.search.emit("input");
  ui.advance(350);
  assert.equal(ui.navigations[0].searchParams.has("q"), false);
  assert.equal(ui.navigations[0].searchParams.get("status"), "all");
});

test("native select change applies pending search immediately without a second navigation", () => {
  const ui = setup("https://example.test/parties/prescribers/?q=Example&status=active");
  ui.search.value = "Dr Example";
  ui.search.emit("input");
  ui.select.value = "inactive";
  ui.form.emit("change", { target: ui.select });
  assert.equal(ui.navigations[0].searchParams.get("q"), "Dr Example");
  assert.equal(ui.navigations[0].searchParams.get("status"), "inactive");
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
