// ===== table.js — Patient table with sorting, filtering, pagination =====
"use strict";

const TABLE_PAGE_SIZE = 20;
let allPatients = [];
let filteredPatients = [];
let currentPage = 1;
let sortKey = "";
let sortDir = 1;

function fmt$(v) { return "$" + Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }); }

function riskLevel(gap) {
  if (gap > 20000) return '<span class="risk-badge risk-high">High</span>';
  if (gap > 5000)  return '<span class="risk-badge risk-medium">Medium</span>';
  return '<span class="risk-badge risk-low">Low</span>';
}

function conditionPill(c) {
  return `<span class="condition-pill">${c || "—"}</span>`;
}

window.initTable = function (patients) {
  allPatients = patients;

  // Populate filter dropdowns
  const states = [...new Set(patients.map((p) => p.State).filter(Boolean))].sort();
  const conds  = [...new Set(patients.map((p) => p.Condition).filter(Boolean))].sort();
  const stateEl = document.getElementById("filter-state");
  const condEl  = document.getElementById("filter-condition");
  if (stateEl) states.forEach((s) => { const o = document.createElement("option"); o.value = o.textContent = s; stateEl.appendChild(o); });
  if (condEl)  conds.forEach((c)  => { const o = document.createElement("option"); o.value = o.textContent = c; condEl.appendChild(o); });

  applyFilters();
};

window.applyFilters = function () {
  const search = (document.getElementById("patient-search")?.value || "").toLowerCase();
  const gender = document.getElementById("filter-gender")?.value || "";
  const state  = document.getElementById("filter-state")?.value || "";
  const cond   = document.getElementById("filter-condition")?.value || "";

  filteredPatients = allPatients.filter((p) => {
    if (gender && p.Gender !== gender) return false;
    if (state  && p.State  !== state)  return false;
    if (cond   && p.Condition !== cond) return false;
    if (search) {
      const hay = `${p.PatientID} ${p.State} ${p.Condition} ${p.Race}`.toLowerCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });

  if (sortKey) {
    filteredPatients.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      return typeof av === "number" ? (av - bv) * sortDir : String(av).localeCompare(String(bv)) * sortDir;
    });
  }

  currentPage = 1;
  renderTable();
  renderPagination();
  const countEl = document.getElementById("filter-count");
  if (countEl) countEl.textContent = `${filteredPatients.length.toLocaleString()} records`;
};

function renderTable() {
  const body = document.getElementById("patients-body");
  if (!body) return;
  const start = (currentPage - 1) * TABLE_PAGE_SIZE;
  const slice = filteredPatients.slice(start, start + TABLE_PAGE_SIZE);

  if (!slice.length) {
    body.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text3);padding:40px">No matching patients found.</td></tr>';
    return;
  }

  body.innerHTML = slice.map((p) => `
    <tr>
      <td><span style="font-family:var(--mono);font-size:12px;color:var(--blue)">${p.PatientID}</span></td>
      <td>${p.Age || "—"}</td>
      <td>${p.Gender || "—"}</td>
      <td>${p.Race || "—"}</td>
      <td>${p.State || "—"}</td>
      <td>${conditionPill(p.Condition)}</td>
      <td><strong>${fmt$(p.Expense)}</strong></td>
      <td>${riskLevel(p.CoverageGap)} <span style="margin-left:6px;font-size:12px;color:var(--text2)">${fmt$(p.CoverageGap)}</span></td>
    </tr>`).join("");
}

function renderPagination() {
  const container = document.getElementById("pagination");
  if (!container) return;
  const total = Math.ceil(filteredPatients.length / TABLE_PAGE_SIZE);
  if (total <= 1) { container.innerHTML = ""; return; }

  let html = `<button class="page-btn" id="pg-prev" ${currentPage === 1 ? "disabled" : ""}>←</button>`;
  const range = 2;
  for (let i = 1; i <= total; i++) {
    if (i === 1 || i === total || Math.abs(i - currentPage) <= range) {
      html += `<button class="page-btn ${i === currentPage ? "active" : ""}" data-page="${i}">${i}</button>`;
    } else if (Math.abs(i - currentPage) === range + 1) {
      html += `<span style="color:var(--text3);padding:0 4px">…</span>`;
    }
  }
  html += `<button class="page-btn" id="pg-next" ${currentPage === total ? "disabled" : ""}>→</button>`;
  container.innerHTML = html;

  container.querySelectorAll("[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => { currentPage = +btn.dataset.page; renderTable(); renderPagination(); });
  });
  document.getElementById("pg-prev")?.addEventListener("click", () => { if (currentPage > 1) { currentPage--; renderTable(); renderPagination(); } });
  document.getElementById("pg-next")?.addEventListener("click", () => { if (currentPage < total) { currentPage++; renderTable(); renderPagination(); } });
}

// Column sort
document.addEventListener("click", (e) => {
  const th = e.target.closest("th[data-sort]");
  if (!th) return;
  const key = th.dataset.sort;
  if (sortKey === key) { sortDir *= -1; } else { sortKey = key; sortDir = 1; }
  applyFilters();
});

// Export CSV
window.exportCSV = function () {
  const headers = ["PatientID","Age","Gender","Race","State","Condition","Expense","CoverageGap"];
  const rows = filteredPatients.map((p) => headers.map((h) => p[h] ?? "").join(","));
  const csv = [headers.join(","), ...rows].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = "patients_export.csv";
  a.click();
};

// Top 10 table
window.renderTop10 = function (rows) {
  const body = document.getElementById("top10-body");
  if (!body || !rows?.length) return;
  body.innerHTML = rows.map((p, i) => `
    <tr>
      <td><span style="font-family:var(--mono);font-size:12px;color:var(--blue)">${p.PatientID}</span></td>
      <td>${p.State}</td>
      <td>${p.Gender}</td>
      <td>${conditionPill(p.Condition)}</td>
      <td><strong style="color:var(--amber)">${fmt$(p.Expense)}</strong></td>
      <td>${fmt$(p.CoverageGap)}</td>
      <td>${riskLevel(p.CoverageGap)}</td>
    </tr>`).join("");
};
