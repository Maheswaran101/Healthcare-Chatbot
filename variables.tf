########################################################################
# variables.tf – root-level inputs
########################################################################

# ── AWS credentials (never hard-code – use TF_VAR_* or terraform.tfvars) ──
variable "aws_access_key" {
  description = "AWS Access Key ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "aws_session_token" {
  description = "AWS Session Token (required for temporary STS/ASIA* credentials)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "aws_secret_key" {
  description = "AWS Secret Access Key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "aws_region" {
  description = "AWS region to deploy all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment tag (dev / staging / prod)"
  type        = string
  default     = "dev"
}

# ── S3 ────────────────────────────────────────────────────────────────
variable "s3_bucket_name" {
  description = "Globally unique S3 bucket name for patient data"
  type        = string
  default     = "healthcare-ai-agent-data-demo"
}

# ── Bedrock ───────────────────────────────────────────────────────────
variable "agent_name" {
  description = "Name of the Bedrock agent"
  type        = string
  default     = "HealthcareAIAgent"
}

variable "foundation_model" {
  description = "Bedrock foundation model ID"
  type        = string
  # Claude 3 Sonnet – widely available for Bedrock Agents
  default = "anthropic.claude-3-sonnet-20240229-v1:0"
}

# ── QuickSight ────────────────────────────────────────────────────────
variable "quicksight_user" {
  description = "QuickSight IAM username (must exist in your account)"
  type        = string
  default     = "healthcare-qs-user"
}

variable "dataset_name" {
  description = "QuickSight dataset display name"
  type        = string
  default     = "healthcare_dataset.csv"
}
