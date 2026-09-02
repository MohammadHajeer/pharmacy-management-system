(() => {
  "use strict";

  if (typeof window.Chart !== "function") return;

  const color = (token) => getComputedStyle(document.documentElement).getPropertyValue(`--color-${token}`).trim();
  const charts = [];
  const number = new Intl.NumberFormat(document.documentElement.lang || "en");
  const fontFamily = getComputedStyle(document.body).fontFamily;

  const metricFormatter = (data) => {
    if (data.currency_code) {
      try {
        return new Intl.NumberFormat(document.documentElement.lang || "en", {
          style: "currency",
          currency: data.currency_code,
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        });
      } catch (error) {
        // A legacy currency code should not prevent the rest of the dashboard rendering.
      }
    }
    return number;
  };

  const analyticsTooltip = (data) => {
    const formatter = metricFormatter(data);
    const base = tooltip(data.unit);
    base.displayColors = data.variant === "grouped-bar" || data.variant === "doughnut";
    base.callbacks.label = (context) => {
      const prefix = context.dataset.label ? `${context.dataset.label}: ` : "";
      const suffix = data.currency_code ? "" : ` ${data.unit}`;
      return `${prefix}${formatter.format(Number(context.raw))}${suffix}`;
    };
    return base;
  };

  const labelScale = (horizontal = false) => ({
    border: { display: true, color: color("line") },
    grid: { display: false },
    ticks: {
      color: color("copy"),
      maxRotation: 0,
      autoSkip: !horizontal,
      padding: 8,
      font: { family: fontFamily, size: 10 },
      ...(horizontal ? {
        callback(value) {
          const label = this.getLabelForValue(value);
          return label.length > 28 ? `${label.slice(0, 27)}…` : label;
        },
      } : {}),
    },
  });

  const valueScale = (data) => {
    const formatter = metricFormatter(data);
    return {
      beginAtZero: true,
      border: { display: false },
      grid: { color: color("chart-grid"), drawTicks: false },
      ticks: {
        color: color("chart-label"),
        maxTicksLimit: 5,
        padding: 8,
        font: { family: fontFamily, size: 10 },
        callback: (value) => formatter.format(Number(value)),
      },
    };
  };

  function analyticsScales(data) {
    if (data.variant === "doughnut") return undefined;
    if (data.horizontal) return { x: valueScale(data), y: labelScale(true) };
    return { x: labelScale(), y: valueScale(data) };
  }

  function renderAnalytics(canvas, data) {
    const toneColor = (tone) => color(`chart-${tone || "sales"}`);
    const baseDataset = {
      borderWidth: 0,
      borderRadius: 6,
      borderSkipped: false,
    };
    let type = "bar";
    let datasets;

    if (data.variant === "grouped-bar") {
      datasets = data.datasets.map((dataset) => ({
        ...baseDataset,
        label: dataset.label,
        data: dataset.values.map(Number),
        backgroundColor: toneColor(dataset.tone),
        hoverBackgroundColor: toneColor(dataset.tone),
        maxBarThickness: 34,
        categoryPercentage: 0.72,
        barPercentage: 0.9,
        dashboardTone: dataset.tone,
      }));
    } else if (data.variant === "doughnut") {
      type = "doughnut";
      datasets = [{
        label: "Posted value",
        data: data.values.map(Number),
        backgroundColor: data.tones.map(toneColor),
        hoverBackgroundColor: data.tones.map(toneColor),
        borderWidth: 0,
        spacing: 2,
        dashboardTones: data.tones,
      }];
    } else if (data.variant === "line") {
      type = "line";
      datasets = [{
        label: "Completed sales",
        data: data.values.map(Number),
        borderColor: toneColor("sales"),
        backgroundColor: toneColor("sales"),
        pointBackgroundColor: toneColor("sales"),
        pointBorderWidth: 0,
        pointRadius: 3,
        pointHoverRadius: 4,
        borderWidth: 2,
        tension: 0.28,
        fill: false,
        dashboardTone: "sales",
      }];
    } else {
      datasets = [{
        ...baseDataset,
        label: "Sold base quantity",
        data: data.values.map(Number),
        backgroundColor: toneColor("sales"),
        hoverBackgroundColor: toneColor("sales"),
        maxBarThickness: 28,
        categoryPercentage: 0.72,
        barPercentage: 0.9,
        dashboardTone: "sales",
      }];
    }

    const chart = new window.Chart(canvas, {
      type,
      data: { labels: data.labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: data.horizontal ? "y" : "x",
        animation: false,
        layout: { padding: { top: 6, right: 6 } },
        interaction: {
          mode: data.variant === "doughnut" ? "nearest" : "index",
          axis: data.horizontal ? "y" : "x",
          intersect: data.variant === "doughnut",
        },
        plugins: {
          legend: { display: false },
          tooltip: analyticsTooltip(data),
        },
        scales: analyticsScales(data),
        ...(data.variant === "doughnut" ? { cutout: "68%", radius: "90%" } : {}),
      },
    });

    const refresh = () => {
      chart.data.datasets.forEach((dataset) => {
        if (dataset.dashboardTones) {
          const colors = dataset.dashboardTones.map(toneColor);
          dataset.backgroundColor = colors;
          dataset.hoverBackgroundColor = colors;
          return;
        }
        const next = toneColor(dataset.dashboardTone);
        if (type === "line") {
          dataset.borderColor = next;
          dataset.pointBackgroundColor = next;
        }
        dataset.backgroundColor = next;
        dataset.hoverBackgroundColor = next;
      });
      chart.options.scales = analyticsScales(data);
      chart.options.plugins.tooltip = analyticsTooltip(data);
    };
    return { chart, refresh };
  }

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
      if (data.variant) {
        charts.push(renderAnalytics(canvas, data));
        return;
      }
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
      charts.push({
        chart,
        refresh() {
          const nextColors = seriesColors();
          chart.data.datasets[0].backgroundColor = nextColors;
          chart.data.datasets[0].hoverBackgroundColor = nextColors;
          chart.options.scales = axes(purchase);
          chart.options.plugins.tooltip = tooltip(data.unit);
        },
      });
    } catch (error) {
      // Keep the server-rendered summary usable if an asset/data problem occurs.
      window.Chart.getChart(canvas)?.destroy();
      container.hidden = true;
      console.warn("Dashboard chart could not be rendered.", error);
    }
  });

  function refreshTheme() {
    charts.forEach(({ chart, refresh }) => {
      refresh();
      chart.update("none");
    });
  }
  document.addEventListener("pharmanex:theme-change", refreshTheme);
  window.addEventListener("beforeprint", refreshTheme);
  window.addEventListener("afterprint", refreshTheme);
})();
