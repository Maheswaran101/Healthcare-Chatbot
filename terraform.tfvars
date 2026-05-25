########################################################################
# terraform.tfvars  –  Fill in your real values, then:
#   terraform init
#   terraform plan
#   terraform apply
#
# SECURITY: Add terraform.tfvars to .gitignore — never commit secrets!
########################################################################

aws_region  = "us-east-1"
environment = "dev"

# ── Paste your IAM user credentials here ─────────────────────────────
aws_access_key = "" # leave blank to use the default AWS profile
aws_secret_key = "" # leave blank to use the default AWS profile

# ── S3 ────────────────────────────────────────────────────────────────
# Using existing bucket in us-east-1 (account 496777887886)
s3_bucket_name = "healthcare-datasets-ai"

# ── Bedrock ───────────────────────────────────────────────────────────
agent_name       = "HealthcareAIAgent"
foundation_model = "anthropic.claude-3-sonnet-20240229-v1:0"

# ── QuickSight ────────────────────────────────────────────────────────
# The IAM username that has QuickSight access in your account
quicksight_user = "AWSReservedSSO_ML-permission_144d0fab99691a25/Maheswaran"
dataset_name    = "Healthcare dashboard"
