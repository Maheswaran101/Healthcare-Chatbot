import { createRequire } from "module";

const require = createRequire(import.meta.url);
const patients = require("../data/mock-patients.json");

export function sendMessage(req, res) {
  const message = String(req.body?.message || "").trim();
  if (!message) {
    res.status(400).json({ error: "Message is required" });
    return;
  }

  const lower = message.toLowerCase();
  if (lower.includes("risk")) {
    const highRisk = patients.filter((patient) => patient.riskScore >= 75).length;
    res.json({ response: `${highRisk} patients are currently in the high risk cohort.` });
    return;
  }

  if (lower.includes("coverage") || lower.includes("gap")) {
    const avgGap = Math.round(patients.reduce((sum, patient) => sum + patient.coverageGap, 0) / patients.length);
    res.json({ response: `The average coverage gap is $${avgGap.toLocaleString("en-US")}.` });
    return;
  }

  if (lower.includes("cost") || lower.includes("expense")) {
    const avgCost = Math.round(patients.reduce((sum, patient) => sum + patient.expense, 0) / patients.length);
    res.json({ response: `Average patient cost is $${avgCost.toLocaleString("en-US")}, with the highest costs concentrated in cardiac and renal care.` });
    return;
  }

  res.json({ response: "I can summarize patient risk, cost trends, and coverage gaps from the dashboard data." });
}
