const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(path.resolve(__dirname, "../../../static/js/dashboard-charts.js"), "utf8");

function page({ library = true, source = true, invalid = false, fail = false, hasData = true } = {}) {
  const container = { hidden: true };
  const canvas = { dataset: { dashboardChart: "stock-health-data" }, closest: () => container };
  const rendered = [];
  const chartData = {
    labels: ["Healthy", "Low stock", "Out of stock"], values: [5, 2, 0],
    tones: ["healthy", "warning", "danger"], unit: "medicines", horizontal: true, has_data: hasData,
  };
  let instance;
  class Chart {
    constructor(node, config) {
      assert.equal(node, canvas);
      if (fail) throw new Error("Canvas unavailable");
      rendered.push(config);
      instance = this;
    }
    static getChart() { return instance; }
  }
  const context = vm.createContext({
    window: library ? { Chart } : {},
    document: {
      documentElement: { lang: "en" }, body: {},
      querySelectorAll: () => [canvas],
      getElementById: () => source ? { textContent: invalid ? "{" : JSON.stringify(chartData) } : null,
    },
    getComputedStyle: () => ({ getPropertyValue: () => "#0f766e", fontFamily: "sans-serif" }),
    Intl, console: { warn() {} },
  });
  return { run: () => vm.runInContext(script, context), rendered, container };
}

test("renders server values with readable integer axes and no duplicate initialization", () => {
  const fixture = page();
  fixture.run();
  fixture.run();
  assert.equal(fixture.rendered.length, 1);
  assert.equal(fixture.container.hidden, false);
  const config = fixture.rendered[0];
  assert.deepEqual(Array.from(config.data.datasets[0].data), [5, 2, 0]);
  assert.equal(config.options.scales.x.ticks.precision, 0);
  assert.equal(config.options.animation, false);
  assert.equal(config.options.plugins.tooltip.callbacks.label({ raw: 1234 }), "1,234 medicines");
});

for (const [name, options] of [
  ["missing library", { library: false }],
  ["missing JSON", { source: false }],
  ["invalid JSON", { invalid: true }],
  ["empty data", { hasData: false }],
  ["canvas failure", { fail: true }],
]) {
  test(`${name} preserves the server summary and hides the unusable canvas`, () => {
    const fixture = page(options);
    assert.doesNotThrow(fixture.run);
    assert.equal(fixture.container.hidden, true);
    assert.equal(fixture.rendered.length, 0);
  });
}
