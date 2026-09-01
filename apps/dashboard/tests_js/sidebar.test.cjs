const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const rootPath = path.resolve(__dirname, "../../..");
const script = fs.readFileSync(path.join(rootPath, "static/js/sidebar.js"), "utf8");

function fixture({ width = 390 } = {}) {
  const documentListeners = {};
  const windowListeners = {};

  function element(attributes = {}) {
    const listeners = {};
    const classes = new Set();
    const attrs = new Map(Object.entries(attributes));
    return {
      listeners,
      focusCount: 0,
      addEventListener(name, callback) { listeners[name] = callback; },
      classList: {
        add(name) { classes.add(name); },
        remove(name) { classes.delete(name); },
        contains(name) { return classes.has(name); },
      },
      focus() { this.focusCount += 1; },
      getAttribute(name) { return attrs.get(name) ?? null; },
      setAttribute(name, value) { attrs.set(name, value); },
    };
  }

  const openButton = element({ "aria-expanded": "false" });
  const closeButton = element();
  const backdrop = element();
  const accountTrigger = element({ "aria-expanded": "false" });
  const logoutButton = element();
  const accountMenu = element();
  accountMenu.open = false;
  accountMenu.contains = (target) => target === accountMenu || target === accountTrigger || target === logoutButton;
  accountMenu.querySelectorAll = () => [logoutButton];
  const sidebar = element();
  sidebar.querySelector = (selector) => ({
    "[data-sidebar-account-menu]": accountMenu,
    "[data-sidebar-account-trigger]": accountTrigger,
  })[selector] ?? null;

  const body = element();
  const document = {
    body,
    addEventListener(name, callback) { documentListeners[name] = callback; },
    querySelector(selector) {
      return ({
        "#dashboard-sidebar": sidebar,
        "#sidebar-backdrop": backdrop,
        "[data-sidebar-open]": openButton,
        "[data-sidebar-close]": closeButton,
      })[selector] ?? null;
    },
  };
  const window = {
    innerWidth: width,
    addEventListener(name, callback) { windowListeners[name] = callback; },
  };

  vm.runInNewContext(script, { document, window });
  documentListeners.DOMContentLoaded();

  return {
    accountMenu,
    accountTrigger,
    body,
    closeButton,
    documentListeners,
    logoutButton,
    openButton,
    sidebar,
  };
}

test("account menu synchronizes state and Escape closes it before the mobile drawer", () => {
  const page = fixture();
  page.openButton.listeners.click();
  assert.equal(page.openButton.getAttribute("aria-expanded"), "true");
  assert.equal(page.body.classList.contains("overflow-hidden"), true);

  page.accountMenu.open = true;
  page.accountMenu.listeners.toggle();
  assert.equal(page.accountTrigger.getAttribute("aria-expanded"), "true");

  page.documentListeners.keydown({ key: "Escape" });
  assert.equal(page.accountMenu.open, false);
  assert.equal(page.accountTrigger.getAttribute("aria-expanded"), "false");
  assert.equal(page.accountTrigger.focusCount, 1);
  assert.equal(page.openButton.getAttribute("aria-expanded"), "true");

  page.documentListeners.keydown({ key: "Escape" });
  assert.equal(page.openButton.getAttribute("aria-expanded"), "false");
  assert.equal(page.body.classList.contains("overflow-hidden"), false);
});

test("outside clicks close the menu and mobile logout closes the drawer before modal handoff", () => {
  const page = fixture();
  page.accountMenu.open = true;
  page.accountMenu.listeners.toggle();
  page.documentListeners.click({ target: {} });
  assert.equal(page.accountMenu.open, false);

  page.openButton.listeners.click();
  page.accountMenu.open = true;
  page.accountMenu.listeners.toggle();
  page.logoutButton.listeners.click();
  assert.equal(page.accountMenu.open, false);
  assert.equal(page.openButton.getAttribute("aria-expanded"), "false");
  assert.equal(page.openButton.focusCount, 1);
});
