########################################################################
# providers.tf – AWS provider with explicit access-key auth
# Supports both permanent (AKIA*) and temporary STS (ASIA*) credentials
########################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}

provider "aws" {
  region = var.aws_region

  access_key = var.aws_access_key != "" ? var.aws_access_key : null
  secret_key = var.aws_secret_key != "" ? var.aws_secret_key : null
  token      = var.aws_session_token != "" ? var.aws_session_token : null
  profile    = var.aws_access_key == "" && var.aws_secret_key == "" ? "default" : null
}

# To use multiple AWS accounts or regions, define additional providers with aliases:
# provider "aws" {
#   alias   = "us_east_1"
#   region  = "us-east-1"
#   profile = "another_profile" # or use environment variables
# }

# Avoid hardcoding credentials in Terraform files. Use environment variables or AWS profiles for authentication.

# ── Handy data sources ──────────────────────────────────────────────────
data "aws_caller_identity" "current" {}
