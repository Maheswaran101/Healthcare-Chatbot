########################################################################
# modules/bedrock/variables.tf
########################################################################
variable "agent_name" { type = string }
variable "foundation_model" { type = string }
variable "s3_bucket_arn" { type = string }
variable "s3_bucket_name" { type = string }
variable "action_handler_lambda_arn" { type = string }
variable "aws_account_id" { type = string }
variable "aws_region" { type = string }
