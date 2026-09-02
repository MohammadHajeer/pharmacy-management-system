const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(path.resolve(__dirname, "../../../static/js/dashboard-charts.js"), "utf8");

function page({ library = true, source = true, invalid = false, fail = false, hasData = true, chart = {} } = {}) {
  const container = { hidden: true };
  const canvas = { dataset: { dashboardChart: "stock-health-data" }, closest: () => container };
  const rendered = [];
  const listeners = {};
  const updates = [];
  let theme = "";
  const chartData = {
    labels: ["Healthy", "Low stock", "Out of stock"], values: [5, 2, 0],
    tones: ["healthy", "warning", "danger"], unit: "medicines", horizontal: false, has_data: hasData, focus_index: 1,
    ...chart,
  };
  let instance;
  class Chart {
    constructor(node, config) {
      assert.equal(node, canvas);
      if (fail) throw new Error("Canvas unavailable");
      rendered.push(config);
      this.data = config.data;
      this.options = config.options;
      instance = this;
    }
    update(mode) { updates.push(mode); }
    static getChart() { return instance; }
  }
  const context = vm.createContext({
    window: { ...(library ? { Chart } : {}), addEventListener: (name, fn) => { listeners[name] = fn; } },
    document: {
      documentElement: { lang: "en" }, body: {},
      querySelectorAll: () => [canvas],
      getElementById: () => source ? { textContent: invalid ? "{" : JSON.stringify(chartData) } : null,
      addEventListener: (name, fn) => { listeners[name] = fn; },
    },
    getComputedStyle: () => ({ getPropertyValue: (token) => theme + token, fontFamily: "sans-serif" }),
    Intl, console: { warn() {} },
  });
  return { run: () => vm.runInContext(script, context), rendered, container, updates,
    emit: (name, value) => { theme = value; listeners[name](); },
  };
}

test("renders server values with readable integer axes and no duplicate initialization", () => {
  const fixture = page();
  fixture.run();
  fixture.run();
  assert.equal(fixture.rendered.length, 1);
  assert.equal(fixture.container.hidden, false);
  const config = fixture.rendered[0];
  assert.deepEqual(Array.from(config.data.datasets[0].data), [5, 2, 0]);
  assert.equal(config.options.scales.y.ticks.precision, 0);
  assert.equal(config.options.animation, false);
  assert.equal(config.options.plugins.tooltip.callbacks.label({ raw: 1234 }), "1,234 medicines");
});

test("stock is three vertical semantic columns with no pastel fills or tracks", () => {
  const fixture = page();
  fixture.run();
  const config = fixture.rendered[0];
  const bars = config.data.datasets[0];
  assert.equal(bars.borderSkipped, false);
  assert.equal(bars.borderRadius, 6);
  assert.equal(config.options.indexAxis, "x");
  assert.equal(bars.maxBarThickness, 64);
  assert.deepEqual(Array.from(bars.backgroundColor), ["--color-chart-healthy", "--color-chart-warning", "--color-chart-danger"]);
  assert.deepEqual(Array.from(config.data.labels), ["Healthy", "Low stock", "Out of stock"]);
  assert.equal(config.options.plugins.legend.display, false);
  assert.equal(config.options.plugins.tooltip.displayColors, false);
  assert.equal(config.options.plugins.tooltip.cornerRadius, 6);
  assert.equal(config.options.plugins.tooltip.bodyFont.weight, "600");
  assert.equal(config.options.plugins.tooltip.borderColor, "--color-chart-tooltip-border");
  assert.equal(config.options.scales.y.ticks.maxTicksLimit, 4);
  assert.equal(config.options.scales.x.ticks.autoSkip, false);
  assert.equal(config.options.interaction.axis, "x");
  assert.equal(config.plugins[0].id, "dashboardValueLabels");
});

test("inventory value labels include zeroes and stay inside the canvas", () => {
  const fixture = page();
  fixture.run();
  const config = fixture.rendered[0];
  assert.equal(config.data.datasets.length, 1);
  assert.equal(config.plugins.length, 1);
  const calls = [];
  const chart = {
    data: config.data,
    ctx: {
      save() { calls.push("save"); }, restore() { calls.push("restore"); },
      measureText: () => ({ width: 12 }), fillText(...args) { calls.push(args); },
    },
    chartArea: { left: 30, right: 300 },
    isDatasetVisible: () => true,
    getDatasetMeta: () => ({ data: [
      { getProps: () => ({ x: 30, y: 20 }) },
      { getProps: () => ({ x: 150, y: 60 }) },
      { getProps: () => ({ x: 300, y: 90 }) },
      { getProps: () => ({ x: NaN, y: 22 }) },
    ] }),
  };
  config.plugins[0].afterDatasetsDraw(chart);
  assert.deepEqual(calls, ["save", ["5", 36, 14], ["2", 150, 54], ["0", 294, 84], "restore"]);
  assert.equal(chart.ctx.fillStyle, "--color-chart-value");
  chart.isDatasetVisible = () => false;
  config.plugins[0].afterDatasetsDraw(chart);
  assert.equal(calls.length, 5);
});

test("purchase columns are wider muted teal with a deep-teal featured month", () => {
  const fixture = page({ chart: { unit: "invoices", tones: ["healthy", "healthy", "healthy"], focus_index: 2 } });
  fixture.run();
  const config = fixture.rendered[0];
  assert.equal(config.type, "bar");
  assert.equal(config.plugins.length, 1);
  assert.equal(config.options.indexAxis, "x");
  assert.equal(config.options.interaction.axis, "x");
  assert.equal(config.options.scales.y.ticks.precision, 0);
  assert.equal(config.options.scales.x.ticks.autoSkip, true);
  assert.equal(config.data.datasets[0].maxBarThickness, 48);
  assert.deepEqual(Array.from(config.data.datasets[0].backgroundColor), ["--color-chart-purchase", "--color-chart-purchase", "--color-chart-focus"]);
  const labels = [];
  config.plugins[0].afterDatasetsDraw({
    data: config.data, chartArea: { left: 0, right: 300 }, isDatasetVisible: () => true,
    ctx: { save() {}, restore() {}, measureText: () => ({ width: 12 }), fillText: (label) => labels.push(label) },
    getDatasetMeta: () => ({ data: [50, 150, 250].map(x => ({ getProps: () => ({ x, y: 100 }) })) }),
  });
  assert.deepEqual(labels, ["0"]);
});

test("expiry isolates urgent buckets without changing counts or using a distorted scale", () => {
  for (const chart of [
    { labels: ["Expired", "0–30 days", "31–90 days", "91+ days"], values: [8, 14, 14, 167], tones: ["danger", "warning", "watch", "neutral"] },
    { labels: ["Expired", "Today", "1+ days"], values: [0, 0, 167], tones: ["danger", "warning", "neutral"] },
  ]) {
    const fixture = page({ chart: { ...chart, unit: "batches" } });
    fixture.run();
    const config = fixture.rendered[0];
    assert.deepEqual(Array.from(config.data.datasets[0].data), chart.values.slice(0, -1));
    assert.deepEqual(Array.from(config.data.labels), chart.labels.slice(0, -1));
    assert.deepEqual(Array.from(config.data.datasets[0].backgroundColor), chart.tones.length === 4
      ? ["--color-chart-danger", "--color-chart-warning", "--color-chart-watch"] : ["--color-chart-danger", "--color-chart-warning"]);
    assert.equal(config.options.scales.y.beginAtZero, true);
    assert.equal(config.options.scales.y.type, undefined); // Chart.js default linear scale.
  }
});

test("sales performance renders Decimal JSON as a restrained currency line", () => {
  const fixture = page({ chart: {
    variant: "line", labels: ["Jan 2026", "Feb 2026"], values: ["125.50", "0.00"],
    tones: ["sales", "sales"], unit: "currency", currency_code: "USD",
  } });
  fixture.run();
  const config = fixture.rendered[0];
  assert.equal(config.type, "line");
  assert.deepEqual(Array.from(config.data.datasets[0].data), [125.5, 0]);
  assert.equal(config.data.datasets[0].borderColor, "--color-chart-sales");
  assert.equal(config.data.datasets[0].tension, 0.28);
  assert.equal(config.options.plugins.legend.display, false);
  assert.equal(config.options.animation, false);
  assert.equal(
    config.options.plugins.tooltip.callbacks.label({ raw: 125.5, dataset: { label: "Completed sales" } }),
    "Completed sales: $125.50",
  );
});

test("commercial comparison uses grouped semantic datasets on one monthly scale", () => {
  const fixture = page({ chart: {
    variant: "grouped-bar", labels: ["Jan 2026", "Feb 2026"], values: [],
    datasets: [
      { label: "Completed sales", values: ["100.00", "0.00"], tone: "sales" },
      { label: "Posted purchases", values: ["42.50", "50.00"], tone: "purchase" },
    ],
    unit: "currency", currency_code: "USD",
  } });
  fixture.run();
  const config = fixture.rendered[0];
  assert.equal(config.type, "bar");
  assert.equal(config.data.datasets.length, 2);
  assert.deepEqual(Array.from(config.data.datasets[0].data), [100, 0]);
  assert.deepEqual(Array.from(config.data.datasets[1].data), [42.5, 50]);
  assert.equal(config.data.datasets[0].backgroundColor, "--color-chart-sales");
  assert.equal(config.data.datasets[1].backgroundColor, "--color-chart-purchase");
  assert.equal(config.data.datasets[0].borderRadius, 6);
  assert.equal(config.options.scales.x.ticks.maxRotation, 0);
});

test("payment mix and top sellers use compact custom chart variants", () => {
  const doughnut = page({ chart: {
    variant: "doughnut", labels: ["Cash", "Card"], values: ["75.00", "25.00"],
    tones: ["series-1", "series-2"], unit: "currency", currency_code: "USD",
  } });
  doughnut.run();
  const doughnutConfig = doughnut.rendered[0];
  assert.equal(doughnutConfig.type, "doughnut");
  assert.equal(doughnutConfig.options.cutout, "68%");
  assert.equal(doughnutConfig.options.scales, undefined);
  assert.deepEqual(Array.from(doughnutConfig.data.datasets[0].backgroundColor), [
    "--color-chart-series-1", "--color-chart-series-2",
  ]);

  const horizontal = page({ chart: {
    variant: "bar", horizontal: true, labels: ["A very long medicine name"], values: ["3.000"],
    tones: ["sales"], unit: "base units", currency_code: "",
  } });
  horizontal.run();
  const horizontalConfig = horizontal.rendered[0];
  assert.equal(horizontalConfig.type, "bar");
  assert.equal(horizontalConfig.options.indexAxis, "y");
  assert.equal(horizontalConfig.data.datasets[0].maxBarThickness, 28);
  assert.equal(horizontalConfig.options.scales.y.ticks.autoSkip, false);
  assert.equal(
    horizontalConfig.options.plugins.tooltip.callbacks.label({ raw: 3, dataset: { label: "Sold base quantity" } }),
    "Sold base quantity: 3 base units",
  );
});

test("analytics theme refresh recolors every dataset without animation", () => {
  const fixture = page({ chart: {
    variant: "grouped-bar", labels: ["Jan 2026"], values: [],
    datasets: [
      { label: "Completed sales", values: ["100.00"], tone: "sales" },
      { label: "Posted purchases", values: ["42.50"], tone: "purchase" },
    ],
    unit: "currency", currency_code: "USD",
  } });
  fixture.run();
  const config = fixture.rendered[0];
  fixture.emit("pharmanex:theme-change", "dark");
  assert.equal(config.data.datasets[0].backgroundColor, "dark--color-chart-sales");
  assert.equal(config.data.datasets[1].backgroundColor, "dark--color-chart-purchase");
  assert.equal(config.options.scales.y.grid.color, "dark--color-chart-grid");
  assert.deepEqual(fixture.updates, ["none"]);
});

test("theme and print changes recolor existing charts instantly without changing counts", () => {
  const fixture = page();
  fixture.run();
  const config = fixture.rendered[0];
  const values = config.data.datasets[0].data;
  for (const [event, theme] of [["pharmanex:theme-change", "dark"], ["beforeprint", "light"], ["afterprint", "dark"]]) {
    fixture.emit(event, theme);
    assert.equal(config.options.scales.y.grid.color, `${theme}--color-chart-grid`);
    assert.equal(config.options.scales.y.ticks.color, `${theme}--color-chart-label`);
    assert.equal(config.options.plugins.tooltip.backgroundColor, `${theme}--color-chart-tooltip`);
    assert.equal(config.data.datasets[0].backgroundColor[0], `${theme}--color-chart-healthy`);
    assert.equal(config.data.datasets[0].data, values);
  }
  assert.deepEqual(fixture.updates, ["none", "none", "none"]);
  assert.equal(fixture.rendered.length, 1);
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
