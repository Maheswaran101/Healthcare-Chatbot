# Healthcare CSV Data Schema

Upload this file to the S3 bucket used by the Bedrock action Lambda.

## healthcare_dataset.csv

```csv
Name,Age,Gender,Blood Type,Medical Condition,Date of Admission,Doctor,Hospital,Insurance Provider,Billing Amount,Room Number,Admission Type,Discharge Date,Medication,Test Results
```

Notes:

- The dataset does not include a native Patient ID, DOB, or phone column.
- The Lambda generates stable row-based IDs such as `P-000001`.
- Patient lookup can use generated `patient_id` or `patient_name`.
- Tools never fabricate missing fields. For example, billing paid/pending values are reported only if columns exist.
