// ===== app.js — Main application orchestrator =====
"use strict";

// ── Utilities ──────────────────────────────────────────────────────────
function fmt$(v) { return "$" + Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }); }

function showToast(msg, type = "info") {
  const t = document.getElementById("toast");
  if (!t) return;
  t.textContent = msg;
  t.className = `toast ${type} show`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 3500);
}

function setStatus(online) {
  const dot   = document.getElementById("status-dot");
  const label = document.getElementById("status-label");
  if (dot)   { dot.className = "status-dot " + (online ? "online" : "error"); }
  if (label) { label.textContent = online ? "Connected" : "Offline"; }
}

function animateValue(el, to) {
  if (!el) return;
  const from = 0;
  const dur  = 900;
  const start = performance.now();
  (function step(now) {
    const p = Math.min((now - start) / dur, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(from + (to - from) * ease).toLocaleString();
    if (p < 1) requestAnimationFrame(step);
    else el.textContent = to.toLocaleString();
  })(start);
}

// ── Tab Navigation ──────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".nav-tab").forEach((b) => {
        b.classList.toggle("active", b.dataset.tab === tab);
        b.setAttribute("aria-selected", b.dataset.tab === tab);
      });
      document.querySelectorAll(".tab-panel").forEach((p) => {
        p.classList.toggle("active", p.id === `panel-${tab}`);
      });
      if (tab === "quicksight") loadQuickSight();
      if (tab === "patients") window.applyFilters?.();
    });
  });
}

// ── KPI Cards ──────────────────────────────────────────────────────────
function renderKPIs(stats) {
  const total  = document.getElementById("kpi-total-value");
  const exp    = document.getElementById("kpi-expense-value");
  const gap    = document.getElementById("kpi-gap-value");
  const states = document.getElementById("kpi-states-value");
  const meta   = document.getElementById("meta-count");

  if (total)  animateValue(total, stats.total_patients);
  if (exp)    { exp.textContent    = fmt$(stats.avg_expense); }
  if (gap)    { gap.textContent    = fmt$(stats.avg_coverage_gap); }
  if (states) { states.textContent = stats.states_count; }
  if (meta)   { meta.textContent   = `${stats.total_patients.toLocaleString()} patients`; }
}

// ── Dashboard Data ──────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const res   = await fetch("/api/stats");
    const stats = await res.json();

    renderKPIs(stats);

    window.renderStateChart?.(stats.state_expenses || []);
    window.renderCoverageChart?.(stats.coverage_split?.covered || 0, stats.coverage_split?.uncovered || 0);
    window.renderGenderChart?.(stats.gender_breakdown || {});
    window.renderAgeChart?.(stats.age_groups || {});

    // Conditions: fetch from patients
    const conditions = Object.entries(
      (stats.condition_breakdown) || {}
    ).map(([Condition, count]) => ({ Condition, count }));
    if (conditions.length) window.renderConditionChart?.(conditions);

    window.renderTop10?.(stats.top10_expensive || []);
    setStatus(true);
  } catch (err) {
    setStatus(false);
    showToast("Could not connect to API. Using fallback data.", "error");
  }
}

async function loadPatients() {
  try {
    const res  = await fetch("/api/patients");
    const data = await res.json();
    window.initTable?.(data);

    // Condition chart from real patient data
    const condMap = {};
    data.forEach((p) => { condMap[p.Condition] = (condMap[p.Condition] || 0) + 1; });
    const condArr = Object.entries(condMap)
      .map(([Condition, count]) => ({ Condition, count }))
      .sort((a, b) => b.count - a.count);
    window.renderConditionChart?.(condArr);
  } catch (err) {
    showToast("Patient data unavailable.", "error");
  }
}

// ── QuickSight (AWS embed only) ─────────────────────────────────────────
async function loadQuickSight() {
  // Statically loaded via HTML to ensure 100% reliable local iframe rendering
  return;
}

// ── Event Listeners ──────────────────────────────────────────────────────
function initEventListeners() {
  document.getElementById("btn-refresh")?.addEventListener("click", async () => {
    showToast("Refreshing data…", "info");
    await Promise.all([loadDashboard(), loadPatients()]);
    showToast("Data refreshed!", "success");
  });

  document.getElementById("btn-export")?.addEventListener("click", () => {
    window.exportCSV?.();
    showToast("CSV exported!", "success");
  });

  document.getElementById("patient-search")?.addEventListener("input",  () => window.applyFilters?.());
  document.getElementById("filter-gender")?.addEventListener("change",  () => window.applyFilters?.());
  document.getElementById("filter-state")?.addEventListener("change",   () => window.applyFilters?.());
  document.getElementById("filter-condition")?.addEventListener("change",() => window.applyFilters?.());
  document.getElementById("btn-clear-filters")?.addEventListener("click", () => {
    ["filter-gender","filter-state","filter-condition"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
    const s = document.getElementById("patient-search");
    if (s) s.value = "";
    window.applyFilters?.();
  });
}

// ── Bootstrap ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  // Init Lucide icons
  if (window.lucide) lucide.createIcons();

  initTabs();
  initEventListeners();
  window.initChat?.();

  // Load data in parallel
  await Promise.all([loadDashboard(), loadPatients()]);

  // Re-init icons after dynamic content
  if (window.lucide) lucide.createIcons();

  showToast("HealthAI dashboard loaded!", "success");
});
