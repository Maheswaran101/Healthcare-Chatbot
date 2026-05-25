########################################################################
# modules/s3/main.tf
# Creates the S3 bucket that stores patient JSON / CSV data
########################################################################

resource "aws_s3_bucket" "healthcare_data" {
  bucket        = var.bucket_name
  force_destroy = true # convenient for demo teardown
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "block" {
  bucket                  = aws_s3_bucket.healthcare_data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "sse" {
  bucket = aws_s3_bucket.healthcare_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versioning
resource "aws_s3_bucket_versioning" "versioning" {
  bucket = aws_s3_bucket.healthcare_data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_object" "healthcare_dataset_manifest" {
  bucket       = aws_s3_bucket.healthcare_data.id
  key          = "manifests/healthcare_dataset_manifest.json"
  content_type = "application/json"

  content = jsonencode({
    fileLocations = [
      {
        URIs = [
          "s3://${aws_s3_bucket.healthcare_data.bucket}/healthcare_dataset.csv"
        ]
      }
    ]
    globalUploadSettings = {
      format         = "CSV"
      delimiter      = ","
      textqualifier  = "\""
      containsHeader = "true"
    }
  })

  depends_on = [aws_s3_bucket_versioning.versioning]
}

# ── Bucket policy: allow QuickSight service principal read access ──────
resource "aws_s3_bucket_policy" "quicksight_read" {
  bucket = aws_s3_bucket.healthcare_data.id
  policy = data.aws_iam_policy_document.bucket_policy.json
}

data "aws_iam_policy_document" "bucket_policy" {
  statement {
    sid    = "AllowQuickSightRead"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["quicksight.amazonaws.com"]
    }

    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.healthcare_data.arn,
      "${aws_s3_bucket.healthcare_data.arn}/*",
    ]
  }

  statement {
    sid    = "AllowBedrockAgentRead"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "s3:PutObject",
    ]

    resources = [
      aws_s3_bucket.healthcare_data.arn,
      "${aws_s3_bucket.healthcare_data.arn}/*",
    ]
  }
}
