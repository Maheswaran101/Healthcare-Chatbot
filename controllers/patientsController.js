import { createRequire } from "module";

const require = createRequire(import.meta.url);
const patients = require("../data/mock-patients.json");

export function getPatients(_req, res) {
  res.json(patients);
}
