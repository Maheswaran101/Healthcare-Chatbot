########################################################################
# modules/bedrock/outputs.tf
########################################################################
output "agent_id" { value = aws_bedrockagent_agent.healthcare_agent.agent_id }
output "agent_arn" { value = aws_bedrockagent_agent.healthcare_agent.agent_arn }
output "agent_alias_id" { value = aws_bedrockagent_agent_alias.demo_alias.agent_alias_id }
output "agent_role_arn" { value = aws_iam_role.bedrock_agent_role.arn }
