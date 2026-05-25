#!/usr/bin/env python3
"""
Upload healthcare dataset assets after terraform apply.

Usage:
  python upload_data.py ^
    --bucket healthcare-ai-agent-data-demo-123456 ^
    --file "d:\\One data\\healthcare_dataset.csv" ^
    --region us-east-1
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path
from typing import Any

import boto3


def clean_nan(obj: Any) -> Any:
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {key: clean_nan(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(item) for item in obj]
    return obj


def healthcare_agent_openapi_schema() -> dict[str, Any]:
    schema_path = Path(__file__).parent / "data" / "healthcare_agent_openapi.json"
    with open(schema_path, encoding="utf-8") as handle:
        return json.load(handle)


def load_as_csv_bytes(source: Path) -> tuple[bytes, int]:
    if source.suffix.lower() == ".csv":
        text = source.read_text(encoding="utf-8-sig")
        row_count = max(0, sum(1 for _ in csv.DictReader(io.StringIO(text))))
        return text.encode("utf-8"), row_count

    with open(source, encoding="utf-8") as handle:
        records = clean_nan(json.load(handle))
    if not isinstance(records, list):
        raise ValueError("JSON input must be a list of records")

    output = io.StringIO()
    if records:
        writer = csv.DictWriter(output, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    return output.getvalue().encode("utf-8"), len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--file", default="healthcare_dataset.csv")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dataset-key", default="healthcare_dataset.csv")
    args = parser.parse_args()

    s3 = boto3.client("s3", region_name=args.region)

    schema = healthcare_agent_openapi_schema()
    schema_key = "schema/healthcare_agent_openapi.json"
    s3.put_object(
        Bucket=args.bucket,
        Key=schema_key,
        Body=json.dumps(schema, indent=2).encode(),
        ContentType="application/json",
    )
    print(f"Uploaded Agent OpenAPI Schema -> s3://{args.bucket}/{schema_key}")

    source = Path(args.file)
    csv_bytes, row_count = load_as_csv_bytes(source)
    s3.put_object(
        Bucket=args.bucket,
        Key=args.dataset_key,
        Body=csv_bytes,
        ContentType="text/csv",
    )
    print(f"Uploaded {row_count} healthcare records -> s3://{args.bucket}/{args.dataset_key}")

    manifest = {
        "fileLocations": [
            {"URIs": [f"s3://{args.bucket}/{args.dataset_key}"]}
        ],
        "globalUploadSettings": {
            "format": "CSV",
            "delimiter": ",",
            "textqualifier": "\"",
            "containsHeader": "true",
        },
    }
    manifest_key = "manifests/healthcare_dataset_manifest.json"
    s3.put_object(
        Bucket=args.bucket,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2).encode(),
        ContentType="application/json",
    )
    print(f"Uploaded QuickSight manifest -> s3://{args.bucket}/{manifest_key}")


if __name__ == "__main__":
    main()
