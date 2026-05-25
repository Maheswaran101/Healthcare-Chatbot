########################################################################
# modules/s3/outputs.tf
########################################################################
output "bucket_name" { value = aws_s3_bucket.healthcare_data.bucket }
output "bucket_arn" { value = aws_s3_bucket.healthcare_data.arn }
output "manifest_key" { value = aws_s3_object.healthcare_dataset_manifest.key }
