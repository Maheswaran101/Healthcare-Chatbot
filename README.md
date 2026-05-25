# Healthcare AI Agent – Amazon Bedrock + QuickSight (Terraform Demo)

## Architecture

```
healthcare_dataset.csv
        │
        ▼
  ┌─────────────┐       Manifest       ┌──────────────────────┐
  │  Amazon S3  │ ──────────────────▶  │  Amazon QuickSight   │
  │  (CSV data) │                      │  DataSource → Dataset│
  └──────┬──────┘                      │  → Dashboard (4 KPIs)│
         │                             └──────────────────────┘
         │ Retrieve context
         ▼
  ┌──────────────────────────────────┐
  │  Amazon Bedrock Agent            │
  │  Model: Claude 3 Sonnet          │
  │  Instruction: Healthcare AI      │
  │  Session TTL: 10 min             │
  └──────────────────────────────────┘
```

## Prerequisites

| Requirement | Notes |
|---|---|
| Terraform ≥ 1.6 | `brew install terraform` / download from hashicorp.com |
| AWS account | IAM user with AdministratorAccess (for demo) |
| Bedrock model access | Enable Claude 3 Sonnet in AWS Console → Bedrock → Model Access |
| QuickSight subscription | Standard or Enterprise in the same region |
| Python 3.9+ + boto3 | `pip install boto3` |

## Step-by-Step Deployment

### 1. Clone / copy this project

```bash
cd healthcare-bedrock-quicksight
```

### 2. Set credentials

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars – fill in your access key, secret key, bucket name, QuickSight user
```

> ⚠️ **Never commit terraform.tfvars to Git.** Add it to `.gitignore`.

### 3. Terraform init & apply

```bash
terraform init
terraform plan
terraform apply -auto-approve
```

After apply, note the outputs:

```
bedrock_agent_id       = "ABCD1234"
bedrock_agent_alias_id = "WXYZ5678"
s3_bucket_name         = "healthcare-ai-agent-data-demo-123456"
quicksight_dataset_arn = "arn:aws:quicksight:..."
quicksight_dashboard_arn = "arn:aws:quicksight:..."
```

### 4. Upload patient data to S3

```bash
python upload_data.py \
  --bucket healthcare-ai-agent-data-demo-123456 \
  --file   "d:\One data\healthcare_dataset.csv" \
  --region us-east-1
```

For the Lambda tool-calling healthcare agent, upload the healthcare CSV at the
bucket root so the action handler can read live records:

```text
s3://<bucket>/healthcare_dataset.csv
```

The expected columns are documented in `data/healthcare_csv_schema.md`.

### 5. Ingest data into QuickSight SPICE

Open AWS Console → QuickSight → Datasets → **PatientHealthcareDataset** → Refresh now.

### 6. View the Dashboard

AWS Console → QuickSight → Dashboards → **Healthcare AI Insights Dashboard**

You'll see:
- 🥧 Gender Distribution (Pie)
- 📊 Patient Count by Medical Condition (Bar)
- 💡 Average Billing Amount (KPI)
- 📊 Billing Amount by Insurance Provider (Bar)

### 7. Chat with the Bedrock Agent

```bash
python invoke_agent.py \
  --agent-id  <bedrock_agent_id from terraform output> \
  --alias-id  <bedrock_agent_alias_id from terraform output> \
  --region    us-east-1
```

Sample questions:
- *"Top diseases this month"*
- *"Which doctor has highest appointments?"*
- *"Give summary of patient P-000001"*
- *"Enaku bill evalo?"*

## File Structure

```
healthcare-bedrock-quicksight/
├── main.tf                        # Root module wiring
├── providers.tf                   # AWS provider + credentials
├── variables.tf                   # All input variables
├── outputs.tf                     # Key resource outputs
├── terraform.tfvars.example       # Fill in and rename to .tfvars
├── upload_data.py                 # Upload healthcare_dataset.csv + manifest to S3
├── invoke_agent.py                # Demo Bedrock agent chat client
├── data/
│   └── manifest.json              # QuickSight S3 manifest template
└── modules/
    ├── s3/                        # S3 bucket + policies
    ├── bedrock/                   # Agent, IAM role, alias
    └── quicksight/                # DataSource, DataSet, Dashboard
```

## Cleanup

```bash
terraform destroy -auto-approve
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `Bedrock model not accessible` | Enable model in Console → Bedrock → Model access |
| `QuickSight user not found` | Run `aws quicksight list-users --aws-account-id <id> --namespace default` to find username |
| `S3 manifest 404` | Run `upload_data.py` before refreshing QuickSight dataset |
| `AccessDenied on Bedrock` | Ensure IAM user has `bedrock:*` permissions |
