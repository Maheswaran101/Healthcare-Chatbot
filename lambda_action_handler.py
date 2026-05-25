"""
Bedrock Agent Action Group Lambda.

Dynamic healthcare dataset tools for Bedrock Agents. The default data source is
one CSV in S3 named healthcare_dataset.csv, matching the Kaggle-style columns:
Name, Age, Gender, Blood Type, Medical Condition, Date of Admission, Doctor,
Hospital, Insurance Provider, Billing Amount, Room Number, Admission Type,
Discharge Date, Medication, Test Results.
"""
from __future__ import annotations

import csv
import io
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

import boto3


s3 = boto3.client("s3")
BUCKET = os.environ.get("DATA_BUCKET", "")
DATASET_KEY = os.environ.get("HEALTHCARE_DATASET_KEY", "healthcare_dataset.csv")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    action_group = event.get("actionGroup", "")
    api_path = event.get("apiPath", "")
    http_method = event.get("httpMethod", "POST")
    function = event.get("function") or str(api_path).strip("/")
    parameters = _event_parameters(event)

    result = dispatch(function, parameters)

    if api_path:
        return {
            "messageVersion": event.get("messageVersion", "1.0"),
            "response": {
                "actionGroup": action_group,
                "apiPath": api_path,
                "httpMethod": http_method,
                "httpStatusCode": 200,
                "responseBody": {
                    "application/json": {"body": json.dumps(result, default=str)}
                },
            },
        }

    return {
        "actionGroup": action_group,
        "function": function,
        "functionResponse": {
            "responseBody": {
                "TEXT": {"body": json.dumps(result, default=str)}
            }
        },
    }


def _event_parameters(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("parameters", [])
    body_properties = (
        event.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("properties", [])
    )
    params: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("name"):
                params[str(item["name"])] = item.get("value", "")
    for item in body_properties:
        if isinstance(item, dict) and item.get("name"):
            params[str(item["name"])] = item.get("value", "")
    return params


def dispatch(function: str, params: dict[str, Any]) -> dict[str, Any]:
    handlers = {
        "get_patient_summary": get_patient_summary,
        "get_patient_billing": get_patient_billing,
        "get_patient_appointments": get_patient_appointments,
        "get_today_appointments": get_today_appointments,
        "get_doctor_analytics": get_doctor_analytics,
        "get_disease_statistics": get_disease_statistics,
        "get_lab_reports": get_lab_reports,
        "get_admission_status": get_admission_status,
        "get_discharge_summary": get_discharge_summary,
        "search_healthcare_records": search_healthcare_records,
        "get_prescription_history": get_prescription_history,
        "get_insurance_details": get_insurance_details,
        "get_revenue_analytics": get_revenue_analytics,
        "get_icu_patients": get_icu_patients,
        "get_critical_alerts": get_critical_alerts,
        # Backward-compatible aliases from the previous project prompt.
        "get_patient_medications": get_prescription_history,
        "get_patient_appointment": get_patient_appointments,
        "get_appointments_today": get_today_appointments,
        "get_doctor_workload": get_doctor_analytics,
        "get_disease_stats": get_disease_statistics,
        "get_billing_analytics": get_revenue_analytics,
        "get_insurance_stats": get_insurance_details,
        "get_flagged_patients": get_critical_alerts,
        "get_clinical_analytics": get_disease_statistics,
        "get_admission_trends": get_admission_trends,
    }
    handler = handlers.get(function)
    if not handler:
        return {"status": "error", "message": f"Unknown function: {function}"}
    try:
        return handler(params)
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def load_dataset() -> list[dict[str, Any]]:
    if not BUCKET:
        return []
    obj = s3.get_object(Bucket=BUCKET, Key=DATASET_KEY)
    content = obj["Body"].read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(content)))
    return [_with_patient_id(row, index) for index, row in enumerate(rows, start=1)]


def _with_patient_id(row: dict[str, Any], index: int) -> dict[str, Any]:
    out = dict(row)
    if not _first(out, ["Patient ID", "patient_id", "PatientID", "ID"]):
        out["patient_id"] = f"P-{index:06d}"
    return out


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _first(row: dict[str, Any], names: list[str], default: str = "") -> str:
    lookup = {_norm(key).replace("_", " "): key for key in row}
    for name in names:
        key = lookup.get(_norm(name).replace("_", " "))
        if key is not None:
            return str(row.get(key) or "").strip()
    return default


def _money(value: Any) -> float:
    try:
        return float(str(value or 0).replace(",", "").replace("$", "").strip() or 0)
    except ValueError:
        return 0.0


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _row_date(row: dict[str, Any], names: list[str]) -> date | None:
    return _parse_date(_first(row, names))


def _patient_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "patient_id": _first(row, ["patient_id", "Patient ID", "PatientID", "ID"]),
        "name": _first(row, ["Name", "patient_name"]),
        "age": _first(row, ["Age"]),
        "gender": _first(row, ["Gender"]),
        "blood_type": _first(row, ["Blood Type", "BloodGroup", "Blood Group"]),
        "diagnosis": _first(row, ["Medical Condition", "Diagnosis", "Condition"]),
        "doctor": _first(row, ["Doctor", "Doctor Assigned"]),
        "hospital": _first(row, ["Hospital"]),
        "insurance_provider": _first(row, ["Insurance Provider"]),
        "billing_amount": _first(row, ["Billing Amount", "Bill Amount", "total_amount"]),
        "room_number": _first(row, ["Room Number", "Room"]),
        "admission_type": _first(row, ["Admission Type"]),
        "admission_date": _first(row, ["Date of Admission", "Admission Date"]),
        "discharge_date": _first(row, ["Discharge Date"]),
        "medication": _first(row, ["Medication", "Medicines", "Prescription"]),
        "test_results": _first(row, ["Test Results", "Lab Results", "Reports"]),
    }


def find_patient(params: dict[str, Any]) -> dict[str, Any] | None:
    rows = load_dataset()
    patient_id = _norm(params.get("patient_id") or params.get("id"))
    patient_name = _norm(params.get("patient_name") or params.get("name"))
    phone = _norm(params.get("phone") or params.get("phone_number"))
    dob = _norm(params.get("dob") or params.get("date_of_birth"))

    for row in rows:
        fields = _patient_fields(row)
        if patient_id and _norm(fields["patient_id"]) == patient_id:
            return row
        if patient_name and patient_name in _norm(fields["name"]):
            if dob and dob not in _norm(_first(row, ["DOB", "Date of Birth", "Birth Date"])):
                continue
            if phone and phone not in _norm(_first(row, ["Phone", "Phone Number", "Mobile"])):
                continue
            return row
    return None


def _find_patient_or_not_found(params: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    patient = find_patient(params)
    if patient:
        return patient, None
    return None, {
        "status": "not_found",
        "message": "No matching patient record found. Please verify Patient ID, full name, DOB, or phone number.",
    }


def _matches_period(row: dict[str, Any], period: str | None) -> bool:
    if not period or period in ("all", "all_time"):
        return True
    admission = _row_date(row, ["Date of Admission", "Admission Date"])
    if not admission:
        return False
    today = date.today()
    if period == "today":
        return admission == today
    if period == "current_month":
        return admission.year == today.year and admission.month == today.month
    if period == "current_year":
        return admission.year == today.year
    return True


def get_patient_summary(params: dict[str, Any]) -> dict[str, Any]:
    patient, error = _find_patient_or_not_found(params)
    if error:
        return error
    fields = _patient_fields(patient or {})
    current_status = "Discharged" if fields["discharge_date"] else "Admitted/Active"
    return {"status": "success", "current_status": current_status, **fields}


def get_patient_billing(params: dict[str, Any]) -> dict[str, Any]:
    patient, error = _find_patient_or_not_found(params)
    if error:
        return error
    fields = _patient_fields(patient or {})
    return {
        "status": "success",
        "patient_id": fields["patient_id"],
        "name": fields["name"],
        "billing_amount": fields["billing_amount"],
        "insurance_provider": fields["insurance_provider"],
        "billing_source": "Billing Amount column",
        "note": "Paid and pending amount columns are not present in this dataset.",
    }


def get_patient_appointments(params: dict[str, Any]) -> dict[str, Any]:
    patient, error = _find_patient_or_not_found(params)
    if error:
        return error
    fields = _patient_fields(patient or {})
    return {
        "status": "success",
        "patient_id": fields["patient_id"],
        "name": fields["name"],
        "appointments": [
            {
                "date": fields["admission_date"],
                "doctor": fields["doctor"],
                "hospital": fields["hospital"],
                "room_number": fields["room_number"],
                "type": fields["admission_type"],
                "status": "Discharged" if fields["discharge_date"] else "Admitted/Active",
            }
        ],
        "note": "This dataset has admission dates, not a separate appointments table.",
    }


def get_today_appointments(params: dict[str, Any]) -> dict[str, Any]:
    today = date.today()
    rows = load_dataset()
    doctor = _norm(params.get("doctor"))
    hospital = _norm(params.get("hospital"))
    todays = []
    for row in rows:
        row_day = _row_date(row, ["Appointment Date", "Date of Appointment", "Date of Admission", "Admission Date"])
        fields = _patient_fields(row)
        if row_day != today:
            continue
        if doctor and doctor not in _norm(fields["doctor"]):
            continue
        if hospital and hospital not in _norm(fields["hospital"]):
            continue
        todays.append(fields)
    return {
        "status": "success",
        "date": str(today),
        "total_appointments": len(todays),
        "records": todays[:100],
        "note": "Counts are based on appointment/admission date columns available in the dataset.",
    }


def get_doctor_analytics(params: dict[str, Any]) -> dict[str, Any]:
    period = _norm(params.get("period") or "all_time")
    rows = [row for row in load_dataset() if _matches_period(row, period)]
    workload = Counter(_patient_fields(row)["doctor"] or "Unknown" for row in rows)
    revenue = defaultdict(float)
    for row in rows:
        fields = _patient_fields(row)
        revenue[fields["doctor"] or "Unknown"] += _money(fields["billing_amount"])
    return {
        "status": "success",
        "period": period,
        "total_records": len(rows),
        "appointments_or_admissions_by_doctor": dict(workload.most_common(20)),
        "revenue_by_doctor": dict(sorted(revenue.items(), key=lambda item: item[1], reverse=True)[:20]),
    }


def get_disease_statistics(params: dict[str, Any]) -> dict[str, Any]:
    period = _norm(params.get("period") or "all_time")
    rows = [row for row in load_dataset() if _matches_period(row, period)]
    diseases = Counter(_patient_fields(row)["diagnosis"] or "Unknown" for row in rows)
    total = len(rows)
    return {
        "status": "success",
        "period": period,
        "total_patients": total,
        "disease_distribution": [
            {"condition": name, "count": count, "percent": round(count / total * 100, 1) if total else 0}
            for name, count in diseases.most_common(20)
        ],
    }


def get_lab_reports(params: dict[str, Any]) -> dict[str, Any]:
    patient, error = _find_patient_or_not_found(params)
    if error:
        return error
    fields = _patient_fields(patient or {})
    return {
        "status": "success",
        "patient_id": fields["patient_id"],
        "name": fields["name"],
        "test_results": fields["test_results"],
        "diagnosis": fields["diagnosis"],
    }


def get_admission_status(params: dict[str, Any]) -> dict[str, Any]:
    patient, error = _find_patient_or_not_found(params)
    if error:
        return error
    fields = _patient_fields(patient or {})
    return {
        "status": "success",
        "patient_id": fields["patient_id"],
        "name": fields["name"],
        "admission_date": fields["admission_date"],
        "discharge_date": fields["discharge_date"],
        "admission_type": fields["admission_type"],
        "room_number": fields["room_number"],
        "current_status": "Discharged" if fields["discharge_date"] else "Admitted/Active",
    }


def get_discharge_summary(params: dict[str, Any]) -> dict[str, Any]:
    patient, error = _find_patient_or_not_found(params)
    if error:
        return error
    fields = _patient_fields(patient or {})
    return {
        "status": "success",
        "patient_id": fields["patient_id"],
        "name": fields["name"],
        "diagnosis": fields["diagnosis"],
        "admission_date": fields["admission_date"],
        "discharge_date": fields["discharge_date"],
        "doctor": fields["doctor"],
        "medication": fields["medication"],
        "test_results": fields["test_results"],
    }


def search_healthcare_records(params: dict[str, Any]) -> dict[str, Any]:
    query = _norm(params.get("query"))
    column = _norm(params.get("column"))
    limit = int(params.get("limit") or 25)
    rows = load_dataset()
    matches = []
    for row in rows:
        if column:
            value = _first(row, [column])
            is_match = query in _norm(value) if query else bool(value)
        else:
            is_match = not query or any(query in _norm(value) for value in row.values())
        if is_match:
            matches.append(_patient_fields(row))
        if len(matches) >= limit:
            break
    return {"status": "success", "query": query, "column": column or None, "count": len(matches), "records": matches}


def get_prescription_history(params: dict[str, Any]) -> dict[str, Any]:
    patient, error = _find_patient_or_not_found(params)
    if error:
        return error
    fields = _patient_fields(patient or {})
    return {
        "status": "success",
        "patient_id": fields["patient_id"],
        "name": fields["name"],
        "medication": fields["medication"],
        "diagnosis": fields["diagnosis"],
        "doctor": fields["doctor"],
        "safety_note": "Do not change medication or dosage without consulting the treating doctor.",
    }


def get_insurance_details(params: dict[str, Any]) -> dict[str, Any]:
    if params.get("patient_id") or params.get("patient_name") or params.get("name"):
        patient, error = _find_patient_or_not_found(params)
        if error:
            return error
        fields = _patient_fields(patient or {})
        return {
            "status": "success",
            "patient_id": fields["patient_id"],
            "name": fields["name"],
            "insurance_provider": fields["insurance_provider"],
            "billing_amount": fields["billing_amount"],
        }
    rows = load_dataset()
    providers = Counter(_patient_fields(row)["insurance_provider"] or "Unknown" for row in rows)
    return {"status": "success", "insurance_provider_distribution": dict(providers.most_common(20))}


def get_revenue_analytics(params: dict[str, Any]) -> dict[str, Any]:
    period = _norm(params.get("period") or "all_time")
    rows = [row for row in load_dataset() if _matches_period(row, period)]
    total = sum(_money(_patient_fields(row)["billing_amount"]) for row in rows)
    by_hospital = defaultdict(float)
    by_insurance = defaultdict(float)
    for row in rows:
        fields = _patient_fields(row)
        by_hospital[fields["hospital"] or "Unknown"] += _money(fields["billing_amount"])
        by_insurance[fields["insurance_provider"] or "Unknown"] += _money(fields["billing_amount"])
    return {
        "status": "success",
        "period": period,
        "total_records": len(rows),
        "revenue_generated": round(total, 2),
        "top_hospitals_by_revenue": dict(sorted(by_hospital.items(), key=lambda item: item[1], reverse=True)[:10]),
        "revenue_by_insurance_provider": dict(sorted(by_insurance.items(), key=lambda item: item[1], reverse=True)[:10]),
    }


def get_icu_patients(params: dict[str, Any]) -> dict[str, Any]:
    rows = load_dataset()
    matches = []
    for row in rows:
        haystack = " ".join(str(value or "") for value in row.values()).lower()
        if "icu" in haystack or "intensive care" in haystack:
            matches.append(_patient_fields(row))
    return {
        "status": "success",
        "count": len(matches),
        "patients": matches[:100],
        "note": "No dedicated ICU column exists in the provided dataset; search used available text fields.",
    }


def get_critical_alerts(params: dict[str, Any]) -> dict[str, Any]:
    rows = load_dataset()
    alerts = []
    for row in rows:
        fields = _patient_fields(row)
        admission_type = _norm(fields["admission_type"])
        test_result = _norm(fields["test_results"])
        if admission_type == "emergency" or test_result in ("abnormal", "critical"):
            alerts.append({
                **fields,
                "alert_reason": "Emergency admission" if admission_type == "emergency" else "Abnormal/Critical test result",
            })
    return {"status": "success", "critical_count": len(alerts), "alerts": alerts[:100]}


def get_admission_trends(params: dict[str, Any]) -> dict[str, Any]:
    months = int(params.get("months") or 6)
    counts: Counter[str] = Counter()
    for row in load_dataset():
        admission = _row_date(row, ["Date of Admission", "Admission Date"])
        if admission:
            counts[f"{admission.year:04d}-{admission.month:02d}"] += 1
    return {"status": "success", "monthly_admissions": dict(sorted(counts.items())[-months:])}
