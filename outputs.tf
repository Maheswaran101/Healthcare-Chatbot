########################################################################
# outputs.tf
########################################################################

output "s3_bucket_name" {
  description = "S3 bucket holding patient data"
  value       = module.s3.bucket_name
}

output "bedrock_agent_id" {
  description = "Bedrock Agent ID"
  value       = module.bedrock.agent_id
}

output "bedrock_agent_alias_id" {
  description = "Bedrock Agent Alias ID (use this in your app)"
  value       = module.bedrock.agent_alias_id
}

output "quicksight_dataset_arn" {
  description = "QuickSight Dataset ARN"
  value       = module.quicksight.dataset_arn
}

output "quicksight_dashboard_arn" {
  description = "QuickSight Dashboard ARN"
  value       = module.quicksight.dashboard_arn
}
