########################################################################
# modules/quicksight/outputs.tf
########################################################################
output "datasource_arn" { value = aws_quicksight_data_source.patients_s3.arn }
output "dataset_arn" { value = aws_quicksight_data_set.patients_dataset.arn }
output "dashboard_arn" { value = aws_quicksight_dashboard.healthcare_dashboard.arn }
