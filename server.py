#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import os
import re
import statistics
from datetime import date, datetime
from collections import Counter, defaultdict
from typing import Any

import boto3
from flask import Flask, jsonify, request, send_from_directory

import requests



AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AGENT_ID = os.getenv("BEDROCK_AGENT_ID", "Q3IT7IQOEX")
AGENT_ALIAS_ID = os.getenv("BEDROCK_AGENT_ALIAS_ID", "OLQQYHBDML")
_DEFAULT_S3_BUCKET = "healthcare-ai-agent-data-demo-123456"
_DEFAULT_S3_PREFIX = "patients/"
S3_BUCKET = os.getenv("PATIENTS_BUCKET", _DEFAULT_S3_BUCKET)
S3_PREFIX = os.getenv("PATIENTS_PREFIX", _DEFAULT_S3_PREFIX)
QUICKSIGHT_ENABLED = os.getenv("QUICKSIGHT_ENABLED", "true").lower() == "true"
QUICKSIGHT_DASHBOARD_ID = os.getenv("QUICKSIGHT_DASHBOARD_ID", "fa366757-9310-4a87-8950-3344d2eceb3c")
# Where patient rows came from (for /api/dataset-info)
LAST_DATA_SOURCE: str = "unknown"
LAST_LOAD_ERROR: str = ""

app = Flask(__name__, static_folder="frontend", static_url_path="")
PATIENT_CACHE: list[dict[str, Any]] | None = None


def _age_from_birthdate(raw: Any) -> int | None:
    """Compute age from common date formats (Synthea / FHIR exports)."""
    if raw is None or str(raw).strip() == "":
        return None
    s = str(raw).strip()[:19]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            birth = datetime.strptime(s[:10], fmt).date()
            today = date.today()
            years = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
            return max(0, years)
        except ValueError:
            continue
    return None


def number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _canonical_gender(raw: Any) -> str:
    """Map F/M, FHIR-style, etc. so counts match QuickSight rollups."""
    if raw is None:
        return "Unknown"
    s = str(raw).strip()
    if not s:
        return "Unknown"
    low = s.lower()
    if low in ("female", "f", "woman"):
        return "Female"
    if low in ("male", "m", "man"):
        return "Male"
    if low in ("other", "non-binary", "nonbinary", "non binary"):
        return "Other"
    if low in ("unknown", "unk", "u"):
        return "Unknown"
    if s in ("Female", "Male", "Other", "Unknown"):
        return s
    return s


def normalize(row: dict[str, Any]) -> dict[str, Any]:
    lower = {key.lower().replace(" ", "_"): value for key, value in row.items()}
    expense = number(lower.get("expense") or lower.get("healthcare_expenses"))
    coverage = number(lower.get("coverage") or lower.get("healthcare_coverage"))
    gap = number(lower.get("coveragegap") or lower.get("coverage_gap"))
    if not gap and expense and coverage:
        gap = max(0.0, expense - coverage)
    age_raw = lower.get("age")
    age_val = int(number(age_raw)) if number(age_raw) else 0
    if not age_val:
        bd = lower.get("birthdate") or lower.get("date_of_birth") or lower.get("birth_date")
        computed = _age_from_birthdate(bd)
        if computed is not None:
            age_val = computed
    gender_raw = (
        lower.get("gender")
        or lower.get("sex")
        or lower.get("administrative_gender")
    )
    return {
        "PatientID": str(
            lower.get("patientid") or lower.get("id") or lower.get("patient_id") or ""
        ).strip(),
        "Gender": _canonical_gender(gender_raw),
        "Race": str(lower.get("race") or "").strip() or "Unknown",
        "State": str(lower.get("state") or "").strip() or "Unknown",
        "Age": age_val,
        "Expense": round(expense, 2),
        "CoverageGap": round(gap, 2),
        "Condition": str(lower.get("condition") or lower.get("encounter_reason") or "").strip()
        or "Unknown",
    }


def parse_object(key: str, body: bytes) -> list[dict[str, Any]]:
    text = body.decode("utf-8-sig").strip()
    if not text:
        return []
    if key.lower().endswith(".csv"):
        return [normalize(row) for row in csv.DictReader(io.StringIO(text))]
    if text.startswith("["):
        return [normalize(row) for row in json.loads(text)]
    return [normalize(json.loads(line)) for line in text.splitlines() if line.strip()]


def _load_patients_env_file() -> None:
    """Load patients.env, then quicksight.env for missing keys (same AWS_PROFILE as QuickSight)."""
    base = os.path.dirname(os.path.abspath(__file__))

    def apply_file(filename: str, override: bool) -> None:
        env_path = os.path.join(base, filename)
        if not os.path.isfile(env_path):
            return
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            if not override and os.environ.get(key):
                continue
            os.environ[key] = value

    apply_file("patients.env", True)
    apply_file("quicksight.env", False)


def _s3_session() -> boto3.Session:
    _load_patients_env_file()
    profile = os.getenv("AWS_PROFILE", "").strip()
    region = os.getenv("AWS_REGION", AWS_REGION)
    if profile:
        return boto3.Session(profile_name=profile, region_name=region)
    return boto3.Session(region_name=region)


def _s3_client():
    return _s3_session().client("s3")


def _s3_bucket_and_prefix() -> tuple[str, str]:
    _load_patients_env_file()
    return (
        os.getenv("PATIENTS_BUCKET", _DEFAULT_S3_BUCKET),
        os.getenv("PATIENTS_PREFIX", _DEFAULT_S3_PREFIX),
    )


def _parse_s3_uri(uri: str) -> tuple[str, str] | None:
    u = uri.strip()
    if not u.lower().startswith("s3://"):
        return None
    rest = u[5:].lstrip("/")
    if "/" not in rest:
        return rest, ""
    bucket, key = rest.split("/", 1)
    return bucket, key


def _load_objects_from_s3_prefix(client: Any, bucket: str, prefix: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if "manifest" in key.lower() or not key.lower().endswith((".csv", ".json")):
                continue
            obj = client.get_object(Bucket=bucket, Key=key)
            rows.extend(parse_object(key, obj["Body"].read()))
    return rows


def _attempt_s3_patients() -> tuple[list[dict[str, Any]] | None, str, str]:
    """
    Load from S3 using the same AWS profile as quicksight.env / patients.env when set.
    Returns (rows_or_none, source_label, error_message).
    """
    try:
        client = _s3_client()
    except Exception as exc:
        return None, "", f"Could not open S3 session (AWS_PROFILE / credentials): {exc}"

    uri = os.getenv("PATIENTS_S3_URI", "").strip()
    if uri:
        parsed = _parse_s3_uri(uri)
        if not parsed:
            return None, "", f"Invalid PATIENTS_S3_URI (use s3://bucket/key or s3://bucket/prefix/): {uri}"
        bucket, key = parsed
        try:
            if not key or key.endswith("/"):
                rows = _load_objects_from_s3_prefix(client, bucket, key or "")
                if rows:
                    return rows, "s3_uri", ""
                return None, "", f"No patient JSON/CSV under s3://{bucket}/{key}"
            rows = parse_object(key, client.get_object(Bucket=bucket, Key=key)["Body"].read())
            if rows:
                return rows, "s3_uri", ""
            return None, "", f"Empty file s3://{bucket}/{key}"
        except Exception as exc:
            return None, "", f"S3 URI load failed: {exc}"

    bucket, prefix = _s3_bucket_and_prefix()
    try:
        rows = _load_objects_from_s3_prefix(client, bucket, prefix)
        if rows:
            return rows, "s3", ""
        return None, "", f"No JSON/CSV objects under s3://{bucket}/{prefix}"
    except Exception as exc:
        return None, "", f"S3 list/get failed: {exc}"


def _load_local_override() -> list[dict[str, Any]] | None:
    override = os.getenv("PATIENTS_LOCAL_OVERRIDE", "").strip()
    if not override:
        return None
    path = override if os.path.isabs(override) else os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), override)
    )
    if not os.path.isfile(path):
        return None
    text = open(path, encoding="utf-8-sig").read().strip()
    if text.startswith("["):
        return [normalize(r) for r in json.loads(text)]
    return [normalize(json.loads(line)) for line in text.splitlines() if line.strip()]


def load_patients(force_refresh: bool = False) -> list[dict[str, Any]]:
    global PATIENT_CACHE, LAST_DATA_SOURCE, LAST_LOAD_ERROR, S3_BUCKET, S3_PREFIX
    if PATIENT_CACHE is not None and not force_refresh:
        return PATIENT_CACHE

    _load_patients_env_file()
    S3_BUCKET = os.getenv("PATIENTS_BUCKET", _DEFAULT_S3_BUCKET)
    S3_PREFIX = os.getenv("PATIENTS_PREFIX", _DEFAULT_S3_PREFIX)
    LAST_LOAD_ERROR = ""

    rows, src, err = _attempt_s3_patients()
    if rows:
        LAST_DATA_SOURCE = src
        LAST_LOAD_ERROR = ""
        PATIENT_CACHE = rows
        return PATIENT_CACHE

    LAST_LOAD_ERROR = err or "Unknown S3 error"

    local_rows = _load_local_override()
    if local_rows:
        LAST_DATA_SOURCE = "local_file"
        LAST_LOAD_ERROR = f"S3 unavailable; using PATIENTS_LOCAL_OVERRIDE. Last S3 error: {err}"
        PATIENT_CACHE = local_rows
        return PATIENT_CACHE

    LAST_DATA_SOURCE = "fallback_error" if err else "fallback_empty_s3"
    PATIENT_CACHE = fallback_patients()
    return PATIENT_CACHE


def fallback_patients() -> list[dict[str, Any]]:
    states = ["MA", "NY", "CA", "TX", "FL", "WA", "IL", "PA", "GA", "NC"]
    genders = ["Female", "Male"]
    races = ["White", "Black", "Asian", "Other"]
    conditions = ["Diabetes", "Hypertension", "Asthma", "Cardiac", "Orthopedic", "Preventive"]
    rows = []
    for index in range(300):
        expense = 12000 + ((index * 791) % 76000)
        gap = max(0, expense - (9000 + ((index * 613) % 62000)))
        rows.append({
            "PatientID": f"P-{index + 1:04d}",
            "Gender": genders[index % len(genders)],
            "Race": races[index % len(races)],
            "State": states[index % len(states)],
            "Age": 8 + ((index * 7) % 82),
            "Expense": float(expense),
            "CoverageGap": float(gap),
            "Condition": conditions[index % len(conditions)],
        })
    return rows


def _get_high_expense_patients_logic(patients: list[dict[str, Any]], limit: int = 10, threshold: float = 0.0) -> list[dict[str, Any]]:
    filtered_patients = [p for p in patients if number(p["Expense"]) >= threshold]
    sorted_patients = sorted(filtered_patients, key=lambda row: number(row["Expense"]), reverse=True)
    return sorted_patients[:limit]

def _get_patients_by_state_logic(patients: list[dict[str, Any]], state: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    if state:
        return [p for p in patients if p["State"].lower() == state.lower()]
    else:
        # Return summary by state, similar to compute_stats' state_expenses
        state_map: dict[str, list[float]] = defaultdict(list)
        for patient in patients:
            state_map[patient["State"]].append(number(patient["Expense"]))
        state_expenses = [
            {"state": s, "avg_expense": round(statistics.mean(values), 2), "count": len(values)}
            for s, values in state_map.items()
        ]
        state_expenses.sort(key=lambda row: row["avg_expense"], reverse=True)
        return state_expenses

def _get_coverage_gap_summary_logic(patients: list[dict[str, Any]], limit: int = 10, threshold: float = 0.0) -> dict[str, Any]:
    filtered_patients = [p for p in patients if number(p["CoverageGap"]) >= threshold]
    sorted_patients = sorted(filtered_patients, key=lambda p: number(p["CoverageGap"]), reverse=True)
    
    gaps = [number(p["CoverageGap"]) for p in filtered_patients]
    avg_gap = round(statistics.mean(gaps), 2) if gaps else 0.0
    
    return {
        "total_patients_with_gap": len(filtered_patients),
        "average_coverage_gap": avg_gap,
        "top_patients_with_gap": sorted_patients[:limit]
    }

def _get_demographics_breakdown_logic(patients: list[dict[str, Any]], group_by: str = "Gender") -> dict[str, Any]:
    if group_by not in ["Gender", "Race"]:
        return {"error": "Invalid groupBy parameter. Must be 'Gender' or 'Race'."}
    
    counts = Counter(p[group_by] for p in patients)
    total = len(patients)
    breakdown = [
        {group_by: key, "count": count, "percent": round((count / total) * 100, 1) if total else 0}
        for key, count in counts.most_common()
    ]
    return {"breakdown": breakdown}

def _get_top_expense_states_logic(patients: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    stats = compute_stats(patients) # compute_stats already has state_expenses
    return stats["state_expenses"][:limit]

def _get_high_risk_patients_logic(patients: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    # Compute high-risk based on multiple clinical and economic factors:
    # Risk Score = (Age * 0.3) + (Expense / 10000 * 0.4) + (CoverageGap / 10000 * 0.3)
    scored = []
    for p in patients:
        age = int(p.get("Age") or 0)
        expense = number(p.get("Expense"))
        gap = number(p.get("CoverageGap"))
        score = (age * 0.3) + (expense / 10000 * 0.4) + (gap / 10000 * 0.3)
        p_copy = dict(p)
        p_copy["RiskScore"] = round(score, 1)
        scored.append(p_copy)
    scored.sort(key=lambda x: x["RiskScore"], reverse=True)
    return scored[:limit]

def _search_patients_logic(patients: list[dict[str, Any]], query: str | None = None, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    results = patients
    if filters:
        for key, value in filters.items():
            results = [p for p in results if str(p.get(key)).lower() == str(value).lower()]
    
    if query:
        query_lower = query.lower()
        results = [
            p for p in results
            if query_lower in str(p.get("PatientID", "")).lower()
            or query_lower in str(p.get("Condition", "")).lower()
            or query_lower in str(p.get("State", "")).lower()
            or query_lower in str(p.get("Gender", "")).lower()
            or query_lower in str(p.get("Race", "")).lower()
        ]
    return results

# Flask routes for action groups
@app.post("/api/action/getHighExpensePatients")
def action_get_high_expense_patients():
    payload = request.get_json(silent=True) or {}
    limit = int(payload.get("limit", 10))
    threshold = float(payload.get("threshold", 0))
    patients = load_patients()
    result = _get_high_expense_patients_logic(patients, limit, threshold)
    return jsonify({"rows": result})

@app.post("/api/action/getPatientsByState")
def action_get_patients_by_state():
    payload = request.get_json(silent=True) or {}
    state = payload.get("state")
    patients = load_patients()
    result = _get_patients_by_state_logic(patients, state)
    return jsonify({"data": result})

@app.post("/api/action/getCoverageGapSummary")
def action_get_coverage_gap_summary():
    payload = request.get_json(silent=True) or {}
    limit = int(payload.get("limit", 10))
    threshold = float(payload.get("threshold", 0))
    patients = load_patients()
    result = _get_coverage_gap_summary_logic(patients, limit, threshold)
    return jsonify(result)

@app.post("/api/action/getDemographicsBreakdown")
def action_get_demographics_breakdown():
    payload = request.get_json(silent=True) or {}
    group_by = payload.get("groupBy", "Gender")
    patients = load_patients()
    result = _get_demographics_breakdown_logic(patients, group_by)
    return jsonify(result)

@app.post("/api/action/getTopExpenseStates")
def action_get_top_expense_states():
    payload = request.get_json(silent=True) or {}
    limit = int(payload.get("limit", 10))
    patients = load_patients()
    result = _get_top_expense_states_logic(patients, limit)
    return jsonify({"rows": result})

@app.post("/api/action/getHighRiskPatients")
def action_get_high_risk_patients():
    payload = request.get_json(silent=True) or {}
    limit = int(payload.get("limit", 10))
    patients = load_patients()
    result = _get_high_risk_patients_logic(patients, limit)
    return jsonify({"rows": result})

@app.post("/api/action/searchPatients")
def action_search_patients():
    payload = request.get_json(silent=True) or {}
    query = payload.get("query")
    filters = payload.get("filters")
    patients = load_patients()
    result = _search_patients_logic(patients, query, filters)
    return jsonify({"rows": result})


def age_groups(patients: list[dict[str, Any]]) -> dict[str, int]:
    groups = {"0-18": 0, "19-35": 0, "36-50": 0, "51-65": 0, "65+": 0}
    for patient in patients:
        age = int(patient.get("Age") or 0)
        if age <= 18:
            groups["0-18"] += 1
        elif age <= 35:
            groups["19-35"] += 1
        elif age <= 50:
            groups["36-50"] += 1
        elif age <= 65:
            groups["51-65"] += 1
        else:
            groups["65+"] += 1
    return groups


def compute_stats(patients: list[dict[str, Any]]) -> dict[str, Any]:
    expenses = [number(p["Expense"]) for p in patients]
    gaps = [number(p["CoverageGap"]) for p in patients]
    state_map: dict[str, list[float]] = defaultdict(list)
    for patient in patients:
        state_map[patient["State"]].append(number(patient["Expense"]))

    state_expenses = [
        {"state": state, "avg_expense": round(statistics.mean(values), 2), "count": len(values)}
        for state, values in state_map.items()
    ]
    state_expenses.sort(key=lambda row: row["avg_expense"], reverse=True)

    top10 = sorted(patients, key=lambda row: number(row["Expense"]), reverse=True)[:10]
    return {
        "total_patients": len(patients),
        "avg_expense": round(statistics.mean(expenses), 2) if expenses else 0,
        "avg_coverage_gap": round(statistics.mean(gaps), 2) if gaps else 0,
        "max_expense": round(max(expenses), 2) if expenses else 0,
        "min_expense": round(min(expenses), 2) if expenses else 0,
        "states_count": len(state_map),
        "gender_breakdown": dict(Counter(p["Gender"] for p in patients)),
        "race_breakdown": dict(Counter(p["Race"] for p in patients)),
        "state_expenses": state_expenses[:10],
        "age_groups": age_groups(patients),
        "top10_expensive": [
            {
                "PatientID": p["PatientID"],
                "State": p["State"],
                "Gender": p["Gender"],
                "Expense": p["Expense"],
                "CoverageGap": p["CoverageGap"],
                "Condition": p["Condition"],
            }
            for p in top10
        ],
        "coverage_split": {
            "covered": sum(1 for p in patients if number(p["CoverageGap"]) <= 0),
            "uncovered": sum(1 for p in patients if number(p["CoverageGap"]) > 0),
        },
    }


def percent_rows(counter: Counter, total: int, label_key: str) -> list[dict[str, Any]]:
    return [
        {label_key: key, "count": count, "percent": round((count / total) * 100, 1) if total else 0}
        for key, count in counter.most_common()
    ]


def _gender_counts_summary(patients: list[dict[str, Any]]) -> str:
    c = Counter(p.get("Gender") or "Unknown" for p in patients)
    order = ["Female", "Male", "Other", "Unknown"]
    parts: list[str] = []
    for key in order:
        if c.get(key):
            parts.append(f"{key} {c[key]}")
    for key, n in sorted(c.items()):
        if key not in order and n:
            parts.append(f"{key} {n}")
    return ", ".join(parts) if parts else "—"


def _not_s3_warning() -> str:
    if LAST_DATA_SOURCE in ("s3", "s3_uri"):
        return ""
    err = (LAST_LOAD_ERROR or "").strip()
    if len(err) > 400:
        err = err[:400] + "…"
    tail = f" S3 error: {err}" if err else ""
    return (
        " Warning: patient data is not loading from S3 (sample data is used). "
        "Create patients.env with AWS_PROFILE (same as QuickSight) and "
        "PATIENTS_S3_URI=s3://your-bucket/path/to/file.json or PATIENTS_BUCKET + PATIENTS_PREFIX. "
        "Then run: aws sso login --profile <name> — restart server — open /api/dataset-info?refresh=1"
        + tail
    )


def local_answer(message: str, patients: list[dict[str, Any]]) -> dict[str, Any]:
    """Analytics answers derived only from the loaded patient dataset (ground truth for chat)."""
    text = message.lower().strip()
    stats = compute_stats(patients)

    # ── Help / Capabilities / Greetings ──
    greetings_triggers = ("what can you do", "help", "capabilities", "what do you do", "hello", "how to use", "who are you", "what are you")
    if any(term in text for term in greetings_triggers) or any(w in text.split() for w in ("hi", "hey")):
        return {
            "response": (
                "👋 Hello! I am your Intelligent AI Healthcare Agent.\n\n"
                "I can dynamically search, filter, and analyze your patient datasets. Here are key things I can do for you:\n"
                "1. **Patient Count:** Ask *'How many patients are there?'*\n"
                "2. **Top Expense Analysis:** Ask *'Show top high expense patients'*\n"
                "3. **State Breakdown:** Ask *'What are the average expenses by state?'*\n"
                "4. **Demographics:** Ask *'Show gender and race distribution'*\n"
                "5. **Coverage Gap:** Ask *'Show patients with coverage gaps'*\n"
                "6. **Conditions:** Ask *'List most common conditions and disease counts'*\n"
                "7. **Age Distribution:** Ask *'Show age group breakdown'*"
            ),
            "intent": "help",
            "data": [],
            "chart_action": "none",
            "filters": {},
        }

    # ── Clinical Knowledge Base (Handling non-analytical healthcare queries offline) ──
    if any(term in text for term in ("compare", "difference", "comparison")):
        return {
            "response": (
                "### Clinical Comparison: Diabetes & Cardiovascular Disease\n\n"
                "Diabetes and Heart Disease are deeply interconnected metabolic and inflammatory conditions:\n\n"
                "1. **Pathophysiology:** Diabetes (specifically hyperglycemia) damages blood vessels over time, leading to microvascular and macrovascular complications. This accelerates plaque buildup (atherosclerosis), which is the primary driver of Coronary Artery Disease (Heart Disease).\n"
                "2. **Risk Correlation:** Individuals with diabetes are **two to four times more likely** to develop cardiovascular issues compared to the general population. The combination of insulin resistance, systemic inflammation, and abnormal lipid levels creates an aggressive profile for vascular damage.\n"
                "3. **Management:** Both require strict lipid management, blood pressure control, and lifestyle interventions. While diabetes focuses on glycemic regulation (HbA1c control), cardiovascular disease management focuses on preventing ischemic events (heart attacks or strokes) through anticoagulants, beta-blockers, or surgical interventions."
            ),
            "intent": "clinical_compare",
            "data": [],
            "chart_action": "none",
            "filters": {},
        }

    if "diabet" in text or "blood sugar" in text or "insulin" in text:
        return {
            "response": (
                "### Understanding Diabetes Mellitus\n\n"
                "Diabetes is a chronic metabolic condition characterized by elevated blood glucose (blood sugar) levels, which can lead to serious cardiovascular, renal, and ocular damage over time.\n\n"
                "*   **Type 1 Diabetes:** An autoimmune condition where the pancreas produces little to no insulin. Patients require daily insulin administration to survive.\n"
                "*   **Type 2 Diabetes:** The most common form, characterized by insulin resistance—where body cells do not respond effectively to insulin. It is strongly linked to lifestyle risk factors, genetics, and obesity.\n"
                "*   **Key Management:** Daily monitoring of blood glucose levels, maintaining healthy dietary choices, regular physical activity, and medical management (such as metformin or insulin therapy) to keep HbA1c levels within target ranges."
            ),
            "intent": "clinical_diabetes",
            "data": [],
            "chart_action": "none",
            "filters": {},
        }

    if "heart" in text or "cardio" in text or "coronary" in text:
        return {
            "response": (
                "### Cardiovascular & Heart Disease Overview\n\n"
                "Heart disease describes a range of conditions that affect your heart, most commonly **Coronary Artery Disease (CAD)**, which affects blood flow to the heart muscle.\n\n"
                "*   **Mechanism:** CAD is caused by atherosclerosis—the buildup of cholesterol plaques inside the coronary arteries, restricting oxygen-rich blood supply. This can lead to chest pain (angina) or a complete blockage resulting in a myocardial infarction (heart attack).\n"
                "*   **Key Symptoms:** Shortness of breath, chest pressure, pain radiating down the left arm or jaw, and extreme fatigue.\n"
                "*   **Prevention & Care:** Maintaining a heart-healthy diet (low saturated fats, high fiber), controlling blood pressure (hypertension), keeping cholesterol low, avoiding tobacco, and engaging in aerobic exercises."
            ),
            "intent": "clinical_heart",
            "data": [],
            "chart_action": "none",
            "filters": {},
        }

    if "asthma" in text or "lung" in text or "respir" in text:
        return {
            "response": (
                "### Understanding Asthma & Respiratory Health\n\n"
                "Asthma is a chronic respiratory condition characterized by airway hyperresponsiveness, bronchospasm, and variable airflow obstruction.\n\n"
                "*   **Pathology:** Triggers (allergens, smoke, cold air, exercise) cause the airways to swell and narrow, accompanied by increased mucus production, leading to wheezing, chest tightness, and coughing.\n"
                "*   **Key Management:** Daily maintenance inhalers (corticosteroids to reduce swelling) and rescue inhalers (bronchodilators to relax airway muscles during attacks)."
            ),
            "intent": "clinical_asthma",
            "data": [],
            "chart_action": "none",
            "filters": {},
        }

    if "hyperten" in text or "blood pressure" in text or any(w == "bp" for w in text.split()):
        return {
            "response": (
                "### Hypertension: The Silent Threat\n\n"
                "Hypertension (commonly known as high blood pressure) is a chronic medical condition where the force of the blood against artery walls is consistently too high.\n\n"
                "*   **Impact:** If left unchecked, it strains the cardiovascular system, accelerating vascular damage and dramatically increasing the risk of strokes, heart failure, and renal disease.\n"
                "*   **Key Prevention:** Adoption of the DASH diet (dietary approaches to stop hypertension), regular physical exercise, sodium restriction, and pharmacological therapy (like ACE inhibitors or beta-blockers)."
            ),
            "intent": "clinical_hypertension",
            "data": [],
            "chart_action": "none",
            "filters": {},
        }

    if any(term in text for term in ("high risk", "risk", "severe", "risk score")):
        high_risk_patients = _get_high_risk_patients_logic(patients, limit=10)
        avg_risk = round(statistics.mean([x["RiskScore"] for x in high_risk_patients]), 1) if high_risk_patients else 0
        return {
            "response": (
                f"### High-Risk Patient Trend Analysis\n\n"
                f"An analysis of the patient records reveals **{len(high_risk_patients)} patients** exhibiting elevated clinical risk profiles. "
                f"The cohort's average comprehensive risk score is **{avg_risk}/10**.\n\n"
                f"*   **Core Drivers:** Elevated age, high healthcare expenditures, and substantial coverage gaps (underinsured parameters).\n"
                f"*   **Top High-Risk Case:** Patient **{high_risk_patients[0]['PatientID']}** (Age {high_risk_patients[0]['Age']}) from state **{high_risk_patients[0]['State']}** exhibits a severe risk factor of **{high_risk_patients[0]['RiskScore']}**."
            ),
            "intent": "high_risk",
            "data": high_risk_patients,
            "chart_action": "highlight_top10",
            "filters": {"RiskScore": "DESC", "limit": 10},
        }

    if any(term in text for term in ("summarize", "summary", "overview")) and any(w in text for w in ("data", "dataset", "patient", "upload")):
        most_common_cond = Counter(p["Condition"] for p in patients).most_common(1)[0][0]
        most_common_state = Counter(p["State"] for p in patients).most_common(1)[0][0]
        return {
            "response": (
                f"### AI-Driven Healthcare Dataset Summary\n\n"
                f"Here is a comprehensive analytical overview of your uploaded healthcare patient records:\n\n"
                f"1. **Cohort Demographics:** A total of **{stats['total_patients']} patients** are currently loaded in the database.\n"
                f"2. **Financial Metrics:** The average patient expense is **${stats['avg_expense']:,.0f}**, with an average coverage gap of **${stats['avg_coverage_gap']:,.0f}**.\n"
                f"3. **Clinical Landscape:** **{most_common_cond}** is the most frequent medical condition matched across the records.\n"
                f"4. **Geographic Distribution:** Patients span **{stats['states_count']} states**, with the highest volume concentrated in **{most_common_state}**.\n"
                f"5. **High Expense State:** **{stats['state_expenses'][0]['state']}** has the highest average patient expense (${stats['state_expenses'][0]['avg_expense']:,.0f})."
            ),
            "intent": "dataset_summary",
            "data": [],
            "chart_action": "none",
            "filters": {},
        }

    # ── Patient Count ──
    if any(term in text for term in ("how many", "patient count", "total patient", "number of patient", "how much patient")):
        return {
            "response": f"Total patient count is {stats['total_patients']}.",
            "intent": "count",
            "data": [{"total_patients": stats["total_patients"]}],
            "chart_action": "pulse_total",
            "filters": {},
        }

    # ── Top Expense / Paid Patients ──
    expensive_trigger = (
        any(term in text for term in ("expense", "paid", "cost", "spend", "charge", "paitent", "patient"))
        and any(term in text for term in ("top", "high", "highest", "most", "largest", "greatest", "paid"))
    )
    if expensive_trigger or "expensive" in text or "expense" in text:
        rows = stats["top10_expensive"]
        if not rows:
            return {
                "response": "No patient expense records found.",
                "intent": "top_expensive",
                "data": [],
                "chart_action": "none",
                "filters": {},
            }
        return {
            "response": (
                f"Top high-expense patients (up to 10): highest expense is "
                f"${rows[0]['Expense']:,.0f} (patient {rows[0].get('PatientID', '—')})."
            ),
            "intent": "top_expensive",
            "data": rows,
            "chart_action": "highlight_top10",
            "filters": {"sort": "Expense DESC", "limit": 10},
        }

    # ── Coverage Gap ──
    if any(term in text for term in ("coverage gap", "gap", "uncovered", "underinsured", "insurance gap")):
        rows = sorted(
            [p for p in patients if number(p["CoverageGap"]) > 0],
            key=lambda p: number(p["CoverageGap"]),
            reverse=True,
        )
        avg_gap = statistics.mean([number(p["CoverageGap"]) for p in rows]) if rows else 0
        return {
            "response": f"{len(rows)} patients have a positive coverage gap. Average gap amount is ${avg_gap:,.0f}.",
            "intent": "coverage_gap",
            "data": rows[:10],
            "chart_action": "highlight_coverage_gap",
            "filters": {"CoverageGap": "> 0"},
        }

    # ── State Breakdown ──
    state_context = (
        any(term in text for term in ("state", "location", "region", "where", "from"))
        or ("state" in text and any(w in text for w in ("expense", "cost", "patient", "average", "breakdown", "distribution")))
    )
    if state_context and stats["state_expenses"]:
        rows = stats["state_expenses"]
        return {
            "response": (
                f"{stats['states_count']} states appear in the data. "
                f"{rows[0]['state']} has the highest average expense (${rows[0]['avg_expense']:,.0f})."
            ),
            "intent": "by_state",
            "data": rows,
            "chart_action": "show_state",
            "filters": {},
        }

    # ── Demographics / Distribution ──
    if any(term in text for term in ("demographics", "gender", "sex", "race", "ethnicity", "distribution")):
        gender = percent_rows(Counter(p["Gender"] for p in patients), len(patients), "Gender")
        race = percent_rows(Counter(p["Race"] for p in patients), len(patients), "Race")
        gtxt = _gender_counts_summary(patients)
        warn = _not_s3_warning()
        return {
            "response": (
                f"Gender distribution ({len(patients)} patients): {gtxt}. "
                f"See the table for percentages. {warn}".strip()
            ),
            "intent": "demographics",
            "data": {"gender": gender, "race": race},
            "chart_action": "show_gender",
            "filters": {},
        }

    # ── Age Groups ──
    if any(term in text for term in ("age", "young", "elder", "senior", "child", "old", "years")):
        return {
            "response": "Age distribution is grouped into five bands (see data).",
            "intent": "age",
            "data": stats["age_groups"],
            "chart_action": "show_age",
            "filters": {},
        }

    # ── Conditions / Diseases ──
    if any(term in text for term in ("condition", "disease", "diagnosis", "illness", "sick", "health", "counts")):
        common = Counter(p["Condition"] for p in patients).most_common()
        rows = [
            {"Condition": key, "count": value}
            for key, value in common
        ]
        top_cond = common[0][0] if common else "Unknown"
        top_count = common[0][1] if common else 0
        return {
            "response": f"The most frequent medical condition in the patient records is **{top_cond}** with **{top_count} cases** out of {len(patients)} total. Here is the full disease count distribution.",
            "intent": "condition",
            "data": rows,
            "chart_action": "show_condition",
            "filters": {},
        }

    return {
        "response": (
            f"This dataset has {stats['total_patients']} patients. "
            f"Average expense ${stats['avg_expense']:,.0f}; average coverage gap ${stats['avg_coverage_gap']:,.0f}.\n\n"
            "💡 **Try asking me about:**\n"
            "• *'How many patients?'*\n"
            "• *'Show top high expense patients'*\n"
            "• *'Average expense by state?'*\n"
            "• *'Show gender and race distribution'*\n"
            "• *'Show patients with coverage gaps'*"
        ),
        "intent": "summary",
        "data": [],
        "chart_action": "none",
        "filters": {},
    }


@app.get("/")
def index() -> Any:
    return send_from_directory("frontend", "index.html")


@app.get("/api/patients")
def api_patients() -> Any:
    if request.args.get("refresh"):
        global PATIENT_CACHE
        PATIENT_CACHE = None
    return jsonify(load_patients())


@app.get("/api/stats")
def api_stats() -> Any:
    return jsonify(compute_stats(load_patients()))


@app.get("/api/dataset-info")
def api_dataset_info() -> Any:
    """Verify S3 upload vs fallback data (same source as dashboard/charts)."""
    global PATIENT_CACHE
    if request.args.get("refresh"):
        PATIENT_CACHE = None
    patients = load_patients(force_refresh=bool(request.args.get("refresh")))
    gb = dict(Counter(p.get("Gender") or "Unknown" for p in patients))
    keys_sample: list[str] = []
    try:
        bkt, pfx = _s3_bucket_and_prefix()
        s3 = _s3_client()
        resp = s3.list_objects_v2(Bucket=bkt, Prefix=pfx, MaxKeys=30)
        for obj in resp.get("Contents") or []:
            k = obj["Key"]
            if "manifest" not in k.lower() and k.lower().endswith((".json", ".csv")):
                keys_sample.append(k)
    except Exception as exc:
        keys_sample = [f"(list failed: {exc})"]
    uri = os.getenv("PATIENTS_S3_URI", "").strip()
    return jsonify(
        {
            "bucket": S3_BUCKET,
            "prefix": S3_PREFIX,
            "patients_s3_uri": uri or None,
            "region": os.getenv("AWS_REGION", AWS_REGION),
            "aws_profile": os.getenv("AWS_PROFILE") or "(default)",
            "row_count": len(patients),
            "data_source": LAST_DATA_SOURCE,
            "last_s3_error": LAST_LOAD_ERROR or None,
            "gender_counts": {k: gb[k] for k in sorted(gb)},
            "s3_patient_file_keys": keys_sample[:15],
            "patient_id_sample": [p.get("PatientID") for p in patients[:3]],
            "note_if_not_quicksight_match": (
                "If gender_counts show 150 Female / 150 Male, you are on sample fallback data. "
                "Configure patients.env (AWS_PROFILE + PATIENTS_S3_URI or bucket/prefix), "
                f"aws sso login, then ?refresh=1. Target bucket: `{S3_BUCKET}`."
                if LAST_DATA_SOURCE not in ("s3", "s3_uri", "local_file")
                else ""
            ),
        }
    )


@app.post("/api/chat")
def api_chat() -> Any:
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    session_id = str(payload.get("session_id") or payload.get("sessionId") or "")
    if not message:
        return jsonify({"response": "Message is required.", "intent": "error", "data": [], "chart_action": "none", "filters": {}}), 400

    # Force refresh ensures we attempt S3 again if the session was just renewed
    patients = load_patients(force_refresh=True)
    local = local_answer(message, patients)
    # Keep local fallback copy in case Bedrock completely errors
    local_response_data = local

    use_bedrock = os.getenv("CHAT_USE_BEDROCK", "0").strip() == "1"
    if not use_bedrock:
        return jsonify(local)

    # --- Bedrock Agent interaction with RETURN_CONTROL handling ---
    bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
    
    # 5. System instruction for prompt engineering to force contextual and non-repetitive answers
    system_instruction = (
        "[System: You are an intelligent Healthcare AI Analytics Agent. "
        "Answer the user's specific question based ONLY on the current question and the dynamic database tools. "
        "Avoid repeating previous responses or model greetings. Generate concise, clinical, healthcare-specific answers. "
        "Do not mention internal database names or tool details. Treat this request with temperature=0.7 and topP=0.9.]"
    )
    
    response_override = None
    tool_invocations = []
    
    while True:
        try:
            # 4. Verify Bedrock invoke payload correctly passes user input, sessionId, agentId, and agentAliasId
            params = {
                "agentId": AGENT_ID,
                "agentAliasId": AGENT_ALIAS_ID,
                "sessionId": session_id,
            }
            
            # Setup session state and pass dynamic model parameters (temperature, topP) in sessionState attributes
            session_state = {
                "sessionAttributes": {
                    "temperature": "0.7",
                    "topP": "0.9"
                }
            }
            
            # 3. Prevent duplicate input or cached loops on control overrides
            if response_override:
                session_state["invocationId"] = response_override["invocationId"]
                session_state["returnControlInvocationResults"] = response_override["results"]
                # For subsequent invocations with return control results, inputText must be omitted
            else:
                params["inputText"] = f"{system_instruction}\nUser Query: {message}"

            params["sessionState"] = session_state

            response = bedrock_agent_runtime.invoke_agent(**params)

            raw_parts = []
            agent_returned_control = False
            for event in response.get("completion", []):
                if "chunk" in event:
                    raw_parts.append(event["chunk"].get("bytes", b"").decode("utf-8"))
                elif "returnControl" in event:
                    agent_returned_control = True
                    rc = event["returnControl"]
                    invocation_id = rc["invocationId"]
                    action_req = rc["agentTool"]["toolInput"]["actionGroupRequest"]
                    api_path = action_req["apiPath"]
                    action_group = action_req.get("actionGroup", "HealthcareActionGroup")
                    http_method = action_req.get("httpMethod", "POST")
                    params_list = action_req.get("parameters", [])
                    parameters = {p["name"]: p["value"] for p in params_list}

                    # Execute local action group logic directly
                    op_id = api_path.lstrip('/')
                    api_res = {}
                    
                    if op_id == "getHighExpensePatients":
                        rows = _get_high_expense_patients_logic(patients, int(parameters.get("limit", 10)), float(parameters.get("threshold", 0)))
                        api_res = {"rows": rows}
                        tool_invocations.append({
                            "intent": "top_expensive",
                            "data": rows,
                            "chart_action": "highlight_top10",
                            "filters": {"sort": "Expense DESC", "limit": parameters.get("limit", 10)}
                        })
                    elif op_id == "getPatientsByState":
                        data = _get_patients_by_state_logic(patients, parameters.get("state"))
                        api_res = {"data": data}
                        tool_invocations.append({
                            "intent": "by_state",
                            "data": data,
                            "chart_action": "show_state",
                            "filters": {}
                        })
                    elif op_id == "getDemographicsBreakdown":
                        res = _get_demographics_breakdown_logic(patients, parameters.get("groupBy", "Gender"))
                        api_res = res
                        gender = percent_rows(Counter(p["Gender"] for p in patients), len(patients), "Gender")
                        race = percent_rows(Counter(p["Race"] for p in patients), len(patients), "Race")
                        tool_invocations.append({
                            "intent": "demographics",
                            "data": {"gender": gender, "race": race},
                            "chart_action": "show_gender",
                            "filters": {}
                        })
                    elif op_id == "searchPatients":
                        rows = _search_patients_logic(patients, parameters.get("query"))
                        api_res = {"rows": rows}
                        tool_invocations.append({
                            "intent": "search",
                            "data": rows,
                            "chart_action": "none",
                            "filters": {}
                        })
                    elif op_id == "getCoverageGapSummary":
                        res = _get_coverage_gap_summary_logic(patients, int(parameters.get("limit", 10)), float(parameters.get("threshold", 0)))
                        api_res = res
                        tool_invocations.append({
                            "intent": "coverage_gap",
                            "data": res.get("top_patients_with_gap", [])[:10],
                            "chart_action": "highlight_coverage_gap",
                            "filters": {"CoverageGap": "> 0"}
                        })
                    elif op_id == "getHighRiskPatients":
                        rows = _get_high_risk_patients_logic(patients, int(parameters.get("limit", 10)))
                        api_res = {"rows": rows}
                        tool_invocations.append({
                            "intent": "high_risk",
                            "data": rows,
                            "chart_action": "highlight_top10",
                            "filters": {"RiskScore": "DESC", "limit": 10}
                        })
                    elif op_id == "getTopExpenseStates":
                        rows = _get_top_expense_states_logic(patients, int(parameters.get("limit", 10)))
                        api_res = {"rows": rows}
                        tool_invocations.append({
                            "intent": "by_state",
                            "data": rows,
                            "chart_action": "show_state",
                            "filters": {}
                        })
                    else:
                        api_res = {"error": f"Unknown action: {op_id}"}

                    # If S3 failed, include the error in the tool response so the agent knows
                    if LAST_LOAD_ERROR and LAST_DATA_SOURCE not in ("s3", "s3_uri"):
                        api_res["_s3_warning"] = f"Using fallback data. S3 Error: {LAST_LOAD_ERROR}"

                    # Pack into Boto3-compliant returnControlInvocationResults format
                    api_res_payload = {
                        "apiResult": {
                            "actionGroup": action_group,
                            "apiPath": api_path,
                            "httpMethod": http_method,
                            "httpStatusCode": 200,
                            "responseBody": {
                                "application/json": {
                                    "body": json.dumps(api_res)
                                }
                            }
                        }
                    }

                    response_override = {
                        "invocationId": invocation_id,
                        "results": [api_res_payload]
                    }
                    break
            
            if not agent_returned_control:
                # This is the final response from the agent
                final_text = "".join(raw_parts).strip()
                
                # 11. Add proper error handling for empty responses
                if not final_text:
                    final_text = local_response_data.get("response", "Could not synthesize dynamic agent answer.")

                if tool_invocations:
                    # Leverage exact tool execution results to construct the visual payload
                    last_tool = tool_invocations[-1]
                    res_data = last_tool["data"]
                    res_chart = last_tool["chart_action"]
                    res_filters = last_tool["filters"]
                    res_intent = last_tool["intent"]
                else:
                    # Clean conversational message - hide any charts/tables to prevent confusion
                    res_data = []
                    res_chart = "none"
                    res_filters = {}
                    res_intent = "bedrock_agent"

                return jsonify({
                    "response": final_text,
                    "intent": res_intent,
                    "data": res_data,
                    "chart_action": res_chart,
                    "filters": res_filters,
                    "source": "bedrock_agent",
                    "model_reply": final_text,
                    "s3_warning_from_server": LAST_LOAD_ERROR if LAST_LOAD_ERROR and LAST_DATA_SOURCE not in ("s3", "s3_uri") else None
                })
        except Exception as exc:
            # 11. Add proper error handling for failed invokeAgent calls and timeout issues
            # In case of absolute bedrock runtime failures, fall back gracefully to local computations
            return jsonify({
                "response": local_response_data.get("response", f"Fallback due to Bedrock runtime error: {exc}"),
                "intent": local_response_data.get("intent", "bedrock_agent_fallback"),
                "data": local_response_data.get("data", []),
                "chart_action": local_response_data.get("chart_action", "none"),
                "filters": local_response_data.get("filters", {}),
                "source": "dataset",
                "model_reply": local_response_data.get("response"),
                "error": str(exc),
                "s3_warning_from_server": LAST_LOAD_ERROR if LAST_LOAD_ERROR and LAST_DATA_SOURCE not in ("s3", "s3_uri") else None
            })


def _load_quicksight_env_file() -> None:
    """Load quicksight.env; QuickSight keys from file override shell env for embed."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quicksight.env")
    if not os.path.isfile(env_path):
        return
    quicksight_keys = {
        "AWS_ACCOUNT_ID",
        "AWS_REGION",
        "AWS_PROFILE",
        "QUICKSIGHT_DASHBOARD_ID",
        "QUICKSIGHT_USER",
        "QUICKSIGHT_USER_ARN",
        "QUICKSIGHT_ALLOWED_DOMAINS",
        "QUICKSIGHT_SESSION_MINUTES",
        "QUICKSIGHT_NAMESPACE",
    }
    with open(env_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            if key in quicksight_keys or key.startswith("QUICKSIGHT_"):
                os.environ[key] = value


def _quicksight_settings() -> dict[str, str]:
    """QuickSight embed settings. Does not affect other API routes."""
    _load_quicksight_env_file()
    region = os.getenv("AWS_REGION", AWS_REGION)
    account_id = os.getenv("AWS_ACCOUNT_ID", "711560820682").strip()
    dashboard_id = os.getenv("QUICKSIGHT_DASHBOARD_ID", "fa366757-9310-4a87-8950-3344d2eceb3c").strip()
    namespace = os.getenv("QUICKSIGHT_NAMESPACE", "default")
    user_arn = os.getenv("QUICKSIGHT_USER_ARN", "").strip()
    if not user_arn:
        qs_user = os.getenv("QUICKSIGHT_USER", "AWSReservedSSO_ML-permission_144d0fab99691a25/Maheswaran").strip()
        user_arn = f"arn:aws:quicksight:{region}:{account_id}:user/{namespace}/{qs_user}"

    return {
        "region": region,
        "account_id": account_id,
        "dashboard_id": dashboard_id,
        "user_arn": user_arn,
        "dashboard_arn": f"arn:aws:quicksight:{region}:{account_id}:dashboard/{dashboard_id}",
    }


def _quicksight_boto_session() -> boto3.Session:
    """Session for QuickSight only; honors AWS_PROFILE from quicksight.env."""
    profile = os.getenv("AWS_PROFILE", "").strip()
    if profile:
        return boto3.Session(profile_name=profile)
    return boto3.Session()


def _quicksight_client(region: str, *, verify_ssl: bool = True):
    """Boto3 QuickSight client."""
    session = _quicksight_boto_session()
    if not verify_ssl:
        return session.client("quicksight", region_name=region, verify=False)
    try:
        import certifi

        return session.client("quicksight", region_name=region, verify=certifi.where())
    except ImportError:
        return session.client("quicksight", region_name=region)


def _generate_quicksight_embed_url(cfg: dict[str, str]) -> dict[str, Any]:
    """Call GenerateEmbedUrlForRegisteredUser; retry without SSL verify on Windows CA issues."""
    payload = {
        "AwsAccountId": cfg["account_id"],
        "SessionLifetimeInMinutes": int(os.getenv("QUICKSIGHT_SESSION_MINUTES", "60")),
        "UserArn": cfg["user_arn"],
        "ExperienceConfiguration": {
            "Dashboard": {"InitialDashboardId": cfg["dashboard_id"]}
        },
        "AllowedDomains": _quicksight_allowed_domains(),
    }
    ssl_disabled = os.getenv("QUICKSIGHT_SSL_VERIFY", "1").strip() == "0"
    client = _quicksight_client(cfg["region"], verify_ssl=not ssl_disabled)
    try:
        return client.generate_embed_url_for_registered_user(**payload)
    except Exception as exc:
        err = str(exc)
        if ssl_disabled or "SSL" not in err and "certificate" not in err.lower():
            raise
        client = _quicksight_client(cfg["region"], verify_ssl=False)
        return client.generate_embed_url_for_registered_user(**payload)


def _quicksight_allowed_domains() -> list[str]:
    raw = os.getenv(
        "QUICKSIGHT_ALLOWED_DOMAINS",
        "http://localhost:5000,http://localhost:8000,http://127.0.0.1:5000,http://127.0.0.1:8000",
    )
    return [domain.strip() for domain in raw.split(",") if domain.strip()]


@app.get("/api/quicksight-url")
def api_quicksight_url() -> Any:
    try:
        cfg = _quicksight_settings()
        response = _generate_quicksight_embed_url(cfg)
        return jsonify(
            {
                "embed_url": response["EmbedUrl"],
                "dashboard_id": cfg["dashboard_id"],
                "is_fallback": False,
            }
        )
    except Exception as exc:
        err = str(exc)
        hint = (
            "Allow http://localhost:8000 in QuickSight → Manage QuickSight → Domains."
        )
        if "SSO session" in err or "UnauthorizedSSOToken" in err:
            profile = os.getenv("AWS_PROFILE", "onedatasoftware-customer-poc")
            hint = (
                f"Run these as two separate commands (do not paste on one line):<br>"
                f"1) aws sso login --profile {profile}<br>"
                f"2) python server.py"
            )
        elif "AccessDenied" in err:
            profile = os.getenv("AWS_PROFILE", "onedatasoftware-customer-poc")
            hint = (
                f"Use quicksight.env AWS_PROFILE={profile}, then run separately:<br>"
                f"1) aws sso login --profile {profile}<br>"
                f"2) python server.py"
            )
        # Graceful fallback to the public shared embed URL provided by the user
        fallback_url = "https://us-east-1.quicksight.aws.amazon.com/sn/account/AkashQS/embed/share/accounts/711560820682/dashboards/fa366757-9310-4a87-8950-3344d2eceb3c"
        return jsonify(
            {
                "embed_url": fallback_url,
                "dashboard_id": cfg.get("dashboard_id", "fa366757-9310-4a87-8950-3344d2eceb3c"),
                "is_fallback": True,
                "error": err,
                "hint": hint,
            }
        )


@app.get("/api/config")
def api_config() -> Any:
    try:
        qs = _quicksight_settings()
        namespace = os.getenv("QUICKSIGHT_NAMESPACE", "AkashQS")
        quicksight_meta = {
            "dashboardArn": qs["dashboard_arn"],
            "dashboardId": qs["dashboard_id"],
            "dashboardUrl": (
                f"https://{qs['region']}.quicksight.aws.amazon.com/sn/account/"
                f"{namespace}/dashboards/{qs['dashboard_id']}"
            ),
            "datasetArn": (
                f"arn:aws:quicksight:{qs['region']}:{qs['account_id']}"
                ":dataset/patients-healthcare-dataset"
            ),
        }
    except Exception:
        quicksight_meta = {}
    return jsonify(
        {
            "region": AWS_REGION,
            "agentId": AGENT_ID,
            "aliasId": AGENT_ALIAS_ID,
            "bucket": S3_BUCKET,
            **quicksight_meta,
        }
    )


if __name__ == "__main__":
    app.run(host="localhost", port=8000, debug=True)
