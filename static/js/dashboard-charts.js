(() => {
  "use strict";

  if (typeof window.Chart !== "function") return;

  const styles = getComputedStyle(document.documentElement);
  const color = (token) => styles.getPropertyValue(`--color-${token}`).trim();
  const palette = {
    healthy: color("primary-700"),
    warning: color("warning"),
    danger: color("danger"),
    watch: color("slate-500"),
    neutral: color("slate-300"),
  };
  const number = new Intl.NumberFormat(document.documentElement.lang || "en");

  document.querySelectorAll("[data-dashboard-chart]").forEach((canvas) => {
    const source = document.getElementById(canvas.dataset.dashboardChart);
    const container = canvas.closest("[data-chart-container]");
    if (!source || !container || window.Chart.getChart(canvas)) return;
    try {
      const data = JSON.parse(source.textContent);
      if (!data.has_data) return;
      container.hidden = false;
      const colors = data.tones.map((tone) => palette[tone]);
      const countAxis = {
        beginAtZero: true,
        suggestedMax: 1,
        border: { display: false },
        grid: { color: color("slate-100") },
        ticks: { precision: 0, color: color("slate-500"), maxTicksLimit: 5 },
      };
      const labelAxis = {
        border: { display: false },
        grid: { display: false },
        ticks: { color: color("slate-600"), maxRotation: 0, autoSkip: !data.horizontal },
      };
      new window.Chart(canvas, {
        type: "bar",
        data: {
          labels: data.labels,
          datasets: [{
            label: data.unit,
            data: data.values,
            backgroundColor: colors,
            hoverBackgroundColor: colors,
            borderWidth: 0,
            borderRadius: 3,
            maxBarThickness: 28,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          indexAxis: data.horizontal ? "y" : "x",
          animation: false,
          font: { family: getComputedStyle(document.body).fontFamily },
          plugins: {
            legend: { display: false },
            tooltip: {
              displayColors: false,
              backgroundColor: color("slate-900"),
              callbacks: {
                label: (context) => `${number.format(context.raw)} ${data.unit}`,
              },
            },
          },
          scales: data.horizontal ? { x: countAxis, y: labelAxis } : { x: labelAxis, y: countAxis },
        },
      });
    } catch (error) {
      // Keep the server-rendered summary usable if an asset/data problem occurs.
      window.Chart.getChart(canvas)?.destroy();
      container.hidden = true;
      console.warn("Dashboard chart could not be rendered.", error);
    }
  });
})();
