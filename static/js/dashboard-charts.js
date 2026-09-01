(() => {
  "use strict";

  if (typeof window.Chart !== "function") return;

  const color = (token) => getComputedStyle(document.documentElement).getPropertyValue(`--color-${token}`).trim();
  const charts = [];
  const number = new Intl.NumberFormat(document.documentElement.lang || "en");
  const fontFamily = getComputedStyle(document.body).fontFamily;

  const tooltip = (unit) => ({
    displayColors: false,
    backgroundColor: color("chart-tooltip"),
    borderColor: color("chart-tooltip-border"),
    borderWidth: 1,
    titleColor: color("chart-tooltip-title"),
    bodyColor: color("chart-tooltip-body"),
    titleFont: { family: fontFamily, size: 11, weight: "normal" },
    bodyFont: { family: fontFamily, size: 12, weight: "600" },
    padding: { x: 10, y: 8 },
    cornerRadius: 6,
    caretSize: 0,
    caretPadding: 6,
    titleMarginBottom: 4,
    callbacks: { label: (context) => `${number.format(context.raw)} ${unit}` },
  });

  function axes(purchase) {
    const count = {
      beginAtZero: true,
      suggestedMax: 1,
      border: { display: false },
      grid: { color: color("chart-grid"), drawTicks: false },
      ticks: { precision: 0, color: color("chart-label"), maxTicksLimit: 4, padding: 8, font: { family: fontFamily, size: 10 } },
    };
    const label = {
      border: { display: true, color: color("line") },
      grid: { display: false },
      ticks: { color: color("copy"), maxRotation: 0, autoSkip: purchase, padding: 8, font: { family: fontFamily, size: 10 } },
    };
    return { x: label, y: count };
  }

  // Exact counts sit above inventory columns; only the featured receipt month
  // is annotated. Values and zeroes come directly from the plotted dataset.
  const valueLabels = (featuredIndex) => ({
    id: "dashboardValueLabels",
    afterDatasetsDraw(chart) {
      const { ctx, chartArea } = chart;
      if (!chartArea || !chart.isDatasetVisible(0)) return;
      ctx.save();
      ctx.font = `600 11px ${fontFamily}`;
      ctx.fillStyle = color("chart-value");
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      chart.getDatasetMeta(0).data.forEach((bar, index) => {
        if (featuredIndex !== undefined && index !== featuredIndex) return;
        const { x, y } = bar.getProps(["x", "y"], true);
        if (!Number.isFinite(x) || !Number.isFinite(y)) return;
        const label = number.format(chart.data.datasets[0].data[index]);
        const halfWidth = ctx.measureText(label).width / 2;
        const labelX = Math.max(chartArea.left + halfWidth, Math.min(chartArea.right - halfWidth, x));
        ctx.fillText(label, labelX, Math.max(14, y - 6));
      });
      ctx.restore();
    },
  });

  document.querySelectorAll("[data-dashboard-chart]").forEach((canvas) => {
    const source = document.getElementById(canvas.dataset.dashboardChart);
    const container = canvas.closest("[data-chart-container]");
    if (!source || !container || window.Chart.getChart(canvas)) return;
    try {
      const data = JSON.parse(source.textContent);
      if (!data.has_data) return;
      container.hidden = false;
      const purchase = data.unit === "invoices";
      // The neutral expiry bucket is shown as a separate, labeled server count.
      // Keep the urgent columns on a linear zero-based scale; never distort it
      // with a broken axis or squeeze them beneath the safe-stock population.
      const indices = data.values.map((_, index) => index).filter((index) => (
        data.unit !== "batches" || data.tones[index] !== "neutral"
      ));
      const seriesColors = () => indices.map((index) => purchase
        ? color(index === data.focus_index ? "chart-focus" : "chart-purchase")
        : color(`chart-${data.tones[index]}`));
      const colors = seriesColors();
      const chart = new window.Chart(canvas, {
        type: "bar",
        plugins: [valueLabels(purchase ? indices.indexOf(data.focus_index) : undefined)],
        data: {
          labels: indices.map((index) => data.labels[index]),
          datasets: [{
            label: data.unit,
            data: indices.map((index) => data.values[index]),
            backgroundColor: colors,
            hoverBackgroundColor: colors,
            borderWidth: 0,
            borderRadius: 6,
            borderSkipped: false,
            maxBarThickness: purchase ? 48 : 64,
            categoryPercentage: purchase ? 0.82 : 0.65,
            barPercentage: 0.9,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          indexAxis: "x",
          animation: false,
          layout: { padding: { top: 20, right: 4 } },
          interaction: { mode: "index", axis: "x", intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: tooltip(data.unit),
          },
          scales: axes(purchase),
        },
      });
      charts.push({ chart, purchase, unit: data.unit, seriesColors });
    } catch (error) {
      // Keep the server-rendered summary usable if an asset/data problem occurs.
      window.Chart.getChart(canvas)?.destroy();
      container.hidden = true;
      console.warn("Dashboard chart could not be rendered.", error);
    }
  });

  function refreshTheme() {
    charts.forEach(({ chart, purchase, unit, seriesColors }) => {
      const colors = seriesColors();
      chart.data.datasets[0].backgroundColor = colors;
      chart.data.datasets[0].hoverBackgroundColor = colors;
      chart.options.scales = axes(purchase);
      chart.options.plugins.tooltip = tooltip(unit);
      chart.update("none");
    });
  }
  document.addEventListener("pharmanex:theme-change", refreshTheme);
  window.addEventListener("beforeprint", refreshTheme);
  window.addEventListener("afterprint", refreshTheme);
})();
