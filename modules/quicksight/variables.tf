########################################################################
# modules/quicksight/variables.tf
########################################################################
variable "aws_account_id" { type = string }
variable "quicksight_user" { type = string }
variable "s3_bucket_arn" { type = string }
variable "s3_bucket_name" { type = string }
variable "manifest_key" { type = string }
variable "dataset_name" { type = string }
variable "aws_region" { type = string }
