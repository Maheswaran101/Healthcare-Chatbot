import { createRequire } from "module";

const require = createRequire(import.meta.url);
const patients = require("../data/mock-patients.json");

export function getStats(_req, res) {
  const totalPatients = patients.length;
  const avgCost = average(patients.map((patient) => patient.expense));
  const coverageGap = average(patients.map((patient) => patient.coverageGap));
  const highRiskPatients = patients.filter((patient) => Number(patient.riskScore) >= 75).length;

  res.json({
    totalPatients,
    avgCost,
    coverageGap,
    highRiskPatients,
    costTrend: [
      { month: "Jan", cost: 188000, claims: 76 },
      { month: "Feb", cost: 214000, claims: 88 },
      { month: "Mar", cost: 204500, claims: 81 },
      { month: "Apr", cost: 239000, claims: 97 },
      { month: "May", cost: 251000, claims: 104 },
      { month: "Jun", cost: 268000, claims: 112 }
    ],
    riskDistribution: [
      { name: "Low", value: patients.filter((patient) => patient.riskScore < 50).length },
      { name: "Medium", value: patients.filter((patient) => patient.riskScore >= 50 && patient.riskScore < 75).length },
      { name: "High", value: highRiskPatients }
    ],
    coverageByState: coverageByState(patients)
  });
}

function average(values) {
  if (!values.length) return 0;
  return Math.round(values.reduce((sum, value) => sum + Number(value || 0), 0) / values.length);
}

function coverageByState(rows) {
  const grouped = rows.reduce((acc, patient) => {
    const state = patient.state || "NA";
    acc[state] ||= { state, gap: 0, patients: 0 };
    acc[state].gap += Number(patient.coverageGap || 0);
    acc[state].patients += 1;
    return acc;
  }, {});

  return Object.values(grouped)
    .map((row) => ({ ...row, gap: Math.round(row.gap / row.patients) }))
    .sort((a, b) => b.gap - a.gap);
}
