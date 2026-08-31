const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

// Small DOM/event fixture: capture, target and bubble listeners share the same
// cancelable event. No dependency or app-specific handler is mocked out.
function setup({ href = "https://example.test/catalog/medicines/?page=2", workspace = true, baseTarget } = {}) {
  class UIEvent {
    constructor(type, options = {}) { Object.assign(this, { type, cancelable: false, defaultPrevented: false }, options); }
    preventDefault() { if (this.cancelable) this.defaultPrevented = true; }
    stopImmediatePropagation() { this.stopped = true; }
  }
  class Element {
    constructor(tag, attrs = {}, parent = null) {
      this.tag = tag;
      this.attrs = new Map(Object.entries(attrs));
      this.parent = parent;
      this.children = [];
      parent?.children.push(this);
      this.handlers = [];
      this.dataset = {};
      this.className = "";
      this.disabled = false;
      this.classList = {
        add: (name) => { this.className = [...new Set([...this.className.split(" ").filter(Boolean), name])].join(" "); },
        remove: (name) => { this.className = this.className.split(" ").filter((item) => item !== name).join(" "); },
      };
    }
    getAttribute(name) { return this.attrs.get(name) ?? null; }
    setAttribute(name, value) { this.attrs.set(name, value); }
    removeAttribute(name) { this.attrs.delete(name); }
    hasAttribute(name) { return this.attrs.has(name); }
    matches(selectors) {
      return selectors.split(",").some((selector) => {
        const match = selector.trim().match(/^(\w+)?(?:\[([^=\]]+)(?:="([^"]*)")?\])?$/);
        return match && (!match[1] || this.tag === match[1])
          && (!match[2] || this.hasAttribute(match[2]))
          && (match[3] === undefined || this.getAttribute(match[2]) === match[3]);
      });
    }
    closest(selector) { return this.matches(selector) ? this : this.parent?.closest(selector) ?? null; }
    querySelectorAll(selector) {
      return this.children.flatMap((child) => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
    addEventListener(type, handler, capture = false) { this.handlers.push({ type, handler, capture }); }
    dispatchEvent(event) {
      event.target = this;
      const path = [this];
      for (let ancestor = this.parent; ancestor; ancestor = ancestor.parent) path.push(ancestor);
      const invoke = (node, capture) => {
        for (const item of node.handlers) {
          if (event.stopped) return;
          if (item.type === event.type && item.capture === capture) item.handler(event);
        }
      };
      for (const node of [...path].reverse()) invoke(node, true);
      for (const node of event.bubbles ? path : [this]) invoke(node, false);
      return !event.defaultPrevented;
    }
  }
  const window = new Element("window");
  window.location = new URL(href);
  const document = new Element("document", {}, window);
  document.baseURI = href;
  const root = new Element("html", { "data-navigation-pending": "true" }, document);
  document.documentElement = root;
  if (baseTarget) new Element("base", { target: baseTarget }, root);
  const main = workspace ? new Element("main", { "data-navigation-workspace": "", "aria-busy": "true" }, root) : null;
  const form = new Element("form", { "data-submit-form": "", method: "post" }, main ?? root);
  const button = new Element("button", { "data-submit-button": "", name: "action", value: "save" }, form);
  const label = new Element("span", { "data-submit-label": "" }, button);
  const loading = new Element("span", { "data-submit-loading": "" }, button);
  loading.className = "hidden";
  let now = 0;
  let sequence = 0;
  const timers = new Map();
  const context = vm.createContext({
    document, window, URL, CustomEvent: UIEvent, Event: UIEvent,
    setTimeout(callback, delay) { const id = ++sequence; timers.set(id, { callback, at: now + delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
  });
  for (const name of ["navigation-loading", "form-submit"]) {
    vm.runInContext(readFileSync(resolve(__dirname, `../../../static/js/${name}.js`), "utf8"), context);
  }
  document.dispatchEvent(new UIEvent("DOMContentLoaded"));
  const emit = (target, type, options) => {
    const event = new UIEvent(type, { bubbles: true, cancelable: true, ...options });
    target.dispatchEvent(event);
    return event;
  };
  return {
    root, main, window, document, form, button, label, loading, timers,
    element: (tag, attrs, parent = root) => new Element(tag, attrs, parent),
    click: (target, options) => emit(target, "click", { button: 0, ...options }),
    submit: (options) => emit(form, "submit", { submitter: button, ...options }),
    navigate: (url) => emit(document, "pharmanex:before-navigate", { detail: { url } }),
    pageshow: (persisted) => emit(window, "pageshow", { persisted }),
    busy: () => root.hasAttribute("data-navigation-pending"),
    advance(ms) {
      now += ms;
      for (const [id, timer] of [...timers]) {
        if (timers.has(id) && timer.at <= now) { timers.delete(id); timer.callback(); }
      }
    },
  };
}

test("initialization resets restored state and auth pages do not install navigation handlers", () => {
  const ui = setup();
  assert.equal(ui.busy(), false);
  assert.equal(ui.main.hasAttribute("aria-busy"), false);
  const auth = setup({ workspace: false });
  auth.root.removeAttribute("data-navigation-pending");
  auth.click(auth.element("a", { href: "/settings/" }));
  assert.equal(auth.busy(), false);
});

test("ordinary nested links, query changes and keyboard clicks preserve default navigation", () => {
  for (const href of ["/settings/", "?page=3", "/catalog/medicines/7/", "https://example.test/finance/"]) {
    const ui = setup();
    const link = ui.element("a", { href });
    const event = ui.click(ui.element("svg", {}, link), { detail: 0 });
    assert.equal(event.defaultPrevented, false);
    assert.equal(ui.busy(), true);
    assert.equal(ui.main.getAttribute("aria-busy"), "true");
    const second = ui.click(ui.element("a", { href: "/parties/suppliers/" }));
    assert.equal(second.defaultPrevented, true);
    assert.equal(second.stopped, true);
  }
});

test("non-navigation links and local controls never start or enter the navigation lock", () => {
  for (const attrs of [
    { href: "https://external.test/" }, { href: "//external.test/path" },
    { href: "mailto:example@example.test" }, { href: "tel:123" }, { href: "javascript:void(0)" },
    { href: "http://[invalid" }, { href: "" }, { href: " #payment-methods" },
    { href: "https://example.test/catalog/medicines/?page=2" },
    { href: "https://example.test/catalog/medicines/?page=2#details" },
    { href: "/settings/", target: "_blank" }, { href: "/settings/", target: "report-frame" },
    { href: "/settings/", download: "" }, { href: "/settings/", "aria-disabled": "true" },
    { href: "/settings/", disabled: "" }, { href: "/settings/", "data-modal-open": "dialog" },
    { href: "/settings/", "aria-haspopup": "dialog" }, { href: "/settings/", role: "button" },
    { href: "/settings/", "data-navigation-loading": "off" },
  ]) {
    const ui = setup();
    const link = ui.element("a", attrs);
    assert.equal(ui.click(link).defaultPrevented, false, JSON.stringify(attrs));
    assert.equal(ui.busy(), false, JSON.stringify(attrs));
    ui.navigate("/finance/");
    assert.equal(ui.click(link).defaultPrevented, false, JSON.stringify(attrs));
  }
  const ui = setup();
  const disabled = ui.element("div", { "aria-disabled": "true" });
  ui.click(ui.element("a", { href: "/settings/" }, disabled));
  assert.equal(ui.busy(), false);
});

test("modified and non-left clicks keep browser behavior even during pending navigation", () => {
  for (const options of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }, { button: 2 }]) {
    const ui = setup();
    const link = ui.element("a", { href: "/settings/" });
    assert.equal(ui.click(link, options).defaultPrevented, false);
    assert.equal(ui.busy(), false);
    ui.navigate("/finance/");
    assert.equal(ui.click(link, options).defaultPrevented, false);
  }
});

test("base targets are respected and explicit _self overrides them", () => {
  const ui = setup({ baseTarget: "_blank" });
  ui.click(ui.element("a", { href: "/settings/" }));
  assert.equal(ui.busy(), false);
  ui.click(ui.element("a", { href: "/settings/", target: "_self" }));
  assert.equal(ui.busy(), true);
});

test("local cancellation, including a later window listener, restores interaction", () => {
  const ui = setup();
  const link = ui.element("a", { href: "/settings/" });
  link.addEventListener("click", (event) => event.preventDefault());
  ui.click(link);
  assert.equal(ui.busy(), false);
  ui.window.addEventListener("click", (event) => event.preventDefault());
  ui.click(ui.element("a", { href: "/finance/" }));
  ui.advance(0);
  assert.equal(ui.busy(), false);
});

test("Back/Forward and 15-second fallback reset locks without extending on repeated clicks", () => {
  for (const recovery of ["back", "forward", "initial", "timeout"]) {
    const ui = setup();
    const link = ui.element("a", { href: "/settings/" });
    ui.click(link);
    ui.advance(10000);
    ui.click(link);
    if (recovery === "timeout") ui.advance(5000);
    else ui.pageshow(recovery !== "initial");
    assert.equal(ui.busy(), false);
    assert.equal(ui.main.hasAttribute("aria-busy"), false);
    ui.click(link);
    assert.equal(ui.busy(), true);
  }
});

test("registry navigation shares the same lock and honors cancellation", () => {
  const ui = setup();
  assert.equal(ui.navigate("?page=3").defaultPrevented, false);
  assert.equal(ui.busy(), true);
  assert.equal(ui.navigate("?q=search").defaultPrevented, true);
  assert.equal(ui.submit().defaultPrevented, true);
  assert.equal(ui.form.dataset.submitting, undefined);
  ui.pageshow(true);
  ui.document.addEventListener("pharmanex:before-navigate", (event) => event.preventDefault());
  assert.equal(ui.navigate("/finance/").defaultPrevented, true);
  ui.advance(0);
  assert.equal(ui.busy(), false);
});

test("native POST and GET submits load even at the same URL, preserving submitter payload", () => {
  for (const method of ["post", "get"]) {
    const ui = setup();
    ui.form.setAttribute("method", method);
    assert.equal(ui.submit().defaultPrevented, false);
    assert.equal(ui.busy(), true);
    assert.equal(ui.form.dataset.submitting, "true");
    assert.equal(ui.button.disabled, false); // browser can serialize action=save
    ui.advance(0);
    assert.equal(ui.button.disabled, true);
    assert.equal(ui.submit().defaultPrevented, true);
    ui.pageshow(true);
    assert.equal(ui.button.disabled, false);
    assert.equal(ui.form.dataset.submitting, undefined);
    assert.equal(ui.label.className, "");
    assert.equal(ui.loading.className, "hidden");
    assert.equal(ui.form.hasAttribute("aria-busy"), false);
  }
});

test("form action, method and browsing-target overrides are honored", () => {
  for (const [attribute, value] of [["formtarget", "_blank"], ["formaction", "https://external.test/"], ["formmethod", "dialog"], ["data-navigation-loading", "off"]]) {
    const ui = setup();
    ui.button.setAttribute(attribute, value);
    ui.submit();
    assert.equal(ui.busy(), false, attribute);
  }
  const ui = setup();
  ui.form.setAttribute("action", "https://external.test/");
  ui.button.setAttribute("formaction", "/settings/");
  ui.submit();
  assert.equal(ui.busy(), true);
});

test("canceled submits and fallback restore button state and re-evaluate dirty forms", () => {
  for (const cancel of [true, false]) {
    const ui = setup();
    ui.form.addEventListener("input", () => { ui.button.disabled = true; });
    if (cancel) ui.window.addEventListener("submit", (event) => event.preventDefault());
    ui.submit();
    ui.advance(cancel ? 0 : 15000);
    assert.equal(ui.busy(), false);
    assert.equal(ui.form.dataset.submitting, undefined);
    assert.equal(ui.button.disabled, true); // dirty helper owns the final state
    assert.equal(ui.loading.className, "hidden");
  }
});
