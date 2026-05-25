// ===== charts.js — Chart rendering with Chart.js =====
"use strict";

const CHART_DEFAULTS = {
  color: "#8892a4",
  grid: "rgba(30,37,54,0.8)",
  blue: "#4f8ef7",
  purple: "#a855f7",
  emerald: "#10b981",
  amber: "#f59e0b",
  red: "#ef4444",
  font: "Inter",
};

Chart.defaults.color = CHART_DEFAULTS.color;
Chart.defaults.font.family = CHART_DEFAULTS.font;
Chart.defaults.font.size = 12;

const PALETTE = [
  "#4f8ef7","#a855f7","#10b981","#f59e0b","#ef4444",
  "#06b6d4","#f97316","#84cc16","#ec4899","#8b5cf6",
];

const chartInstances = {};

function destroyChart(id) {
  if (chartInstances[id]) {
    chartInstances[id].destroy();
    delete chartInstances[id];
  }
}

function makeTooltip() {
  return {
    backgroundColor: "#0e1117",
    borderColor: "#1e2536",
    borderWidth: 1,
    titleColor: "#e8ecf4",
    bodyColor: "#8892a4",
    padding: 10,
    cornerRadius: 8,
    displayColors: true,
    boxWidth: 10,
    boxHeight: 10,
  };
}

// Bar chart: state expenses
window.renderStateChart = function (data) {
  destroyChart("state");
  const labels = data.map((d) => d.state);
  const values = data.map((d) => d.avg_expense);
  const ctx = document.getElementById("chart-state");
  if (!ctx) return;

  chartInstances["state"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Avg Expense ($)",
        data: values,
        backgroundColor: labels.map((_, i) => PALETTE[i % PALETTE.length] + "cc"),
        borderColor: labels.map((_, i) => PALETTE[i % PALETTE.length]),
        borderWidth: 1,
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          ...makeTooltip(),
          callbacks: {
            label: (ctx) => ` $${Number(ctx.parsed.y).toLocaleString()}`,
          },
        },
      },
      scales: {
        x: { grid: { color: CHART_DEFAULTS.grid }, ticks: { maxRotation: 0 } },
        y: {
          grid: { color: CHART_DEFAULTS.grid },
          ticks: { callback: (v) => "$" + (v / 1000).toFixed(0) + "k" },
        },
      },
    },
  });
};

// Doughnut: coverage
window.renderCoverageChart = function (covered, uncovered) {
  destroyChart("coverage");
  const ctx = document.getElementById("chart-coverage");
  if (!ctx) return;

  chartInstances["coverage"] = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Covered", "Uncovered"],
      datasets: [{
        data: [covered, uncovered],
        backgroundColor: ["#10b98133", "#ef444433"],
        borderColor: ["#10b981", "#ef4444"],
        borderWidth: 2,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "70%",
      plugins: {
        legend: { display: false },
        tooltip: { ...makeTooltip() },
      },
    },
  });

  // Custom legend
  const legend = document.getElementById("coverage-legend");
  if (legend) {
    const total = covered + uncovered;
    legend.innerHTML = `
      <div class="coverage-legend-item">
        <div class="legend-dot" style="background:#10b981"></div>
        Covered ${total ? Math.round((covered/total)*100) : 0}%
      </div>
      <div class="coverage-legend-item">
        <div class="legend-dot" style="background:#ef4444"></div>
        Gap ${total ? Math.round((uncovered/total)*100) : 0}%
      </div>`;
  }
};

// Pie: gender
window.renderGenderChart = function (data) {
  destroyChart("gender");
  const ctx = document.getElementById("chart-gender");
  if (!ctx) return;

  chartInstances["gender"] = new Chart(ctx, {
    type: "pie",
    data: {
      labels: Object.keys(data),
      datasets: [{
        data: Object.values(data),
        backgroundColor: ["#4f8ef733","#a855f733"],
        borderColor: ["#4f8ef7","#a855f7"],
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, padding: 14 } },
        tooltip: { ...makeTooltip() },
      },
    },
  });
};

// Bar: age groups
window.renderAgeChart = function (data) {
  destroyChart("age");
  const ctx = document.getElementById("chart-age");
  if (!ctx) return;

  chartInstances["age"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels: Object.keys(data),
      datasets: [{
        label: "Patients",
        data: Object.values(data),
        backgroundColor: PALETTE.map((c) => c + "99"),
        borderColor: PALETTE,
        borderWidth: 1,
        borderRadius: 5,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { ...makeTooltip() } },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: CHART_DEFAULTS.grid }, ticks: { maxTicksLimit: 5 } },
      },
    },
  });
};

// Horizontal bar: conditions
window.renderConditionChart = function (data) {
  destroyChart("condition");
  const ctx = document.getElementById("chart-condition");
  if (!ctx) return;

  chartInstances["condition"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map((d) => d.Condition),
      datasets: [{
        label: "Patients",
        data: data.map((d) => d.count),
        backgroundColor: PALETTE.map((c) => c + "99"),
        borderColor: PALETTE,
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { ...makeTooltip() } },
      scales: {
        x: { grid: { color: CHART_DEFAULTS.grid } },
        y: { grid: { display: false } },
      },
    },
  });
};
