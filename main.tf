########################################################################
# Healthcare AI Agent – Bedrock + QuickSight  (Demo)
# Author : Maheswaran
# Stack  : Terraform  ≥ 1.6
########################################################################

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

module "s3" {
  source      = "./modules/s3"
  bucket_name = var.s3_bucket_name
}

data "archive_file" "lambda_action_handler" {
  type        = "zip"
  source_file = "${path.root}/lambda_action_handler.py"
  output_path = "${path.root}/.terraform/lambda_action_handler.zip"
}

resource "aws_iam_role" "lambda_action_handler" {
  name = "${var.agent_name}-action-handler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda_action_handler" {
  name = "${var.agent_name}-action-handler-policy"
  role = aws_iam_role.lambda_action_handler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          module.s3.bucket_arn,
          "${module.s3.bucket_arn}/*"
        ]
      }
    ]
  })
}

resource "aws_lambda_function" "action_handler" {
  function_name    = "${var.agent_name}-action-handler"
  role             = aws_iam_role.lambda_action_handler.arn
  handler          = "lambda_action_handler.lambda_handler"
  runtime          = "python3.11"
  filename         = data.archive_file.lambda_action_handler.output_path
  source_code_hash = data.archive_file.lambda_action_handler.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      DATA_BUCKET            = module.s3.bucket_name
      HEALTHCARE_DATASET_KEY = "healthcare_dataset.csv"
    }
  }
}

module "bedrock" {
  source                    = "./modules/bedrock"
  agent_name                = var.agent_name
  foundation_model          = var.foundation_model
  s3_bucket_arn             = module.s3.bucket_arn
  s3_bucket_name            = module.s3.bucket_name
  action_handler_lambda_arn = aws_lambda_function.action_handler.arn
  aws_account_id            = data.aws_caller_identity.current.account_id
  aws_region                = var.aws_region
}

# ── QuickSight is optional ────────────────────────────────────────────
# QuickSight requires a separate subscription in the AWS Console.
# Sign up at: https://us-east-1.quicksight.aws.amazon.com/
# Once subscribed, uncomment the block below and re-run terraform apply.
#
module "quicksight" {
  source          = "./modules/quicksight"
  aws_account_id  = data.aws_caller_identity.current.account_id
  quicksight_user = var.quicksight_user
  s3_bucket_arn   = module.s3.bucket_arn
  s3_bucket_name  = module.s3.bucket_name
  manifest_key    = module.s3.manifest_key
  dataset_name    = var.dataset_name
  aws_region      = var.aws_region
}
