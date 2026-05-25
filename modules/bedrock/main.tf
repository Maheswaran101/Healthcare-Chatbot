########################################################################
# modules/bedrock/main.tf
# Bedrock Agent with IAM role + inline instruction
########################################################################

###############################################
# 1.  IAM Role for the Bedrock Agent
###############################################
resource "aws_iam_role" "bedrock_agent_role" {
  name = "${var.agent_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = var.aws_account_id
        }
        ArnLike = {
          "aws:SourceArn" = "arn:aws:bedrock:${var.aws_region}:${var.aws_account_id}:agent/*"
        }
      }
    }]
  })
}

# Allow the agent to call Bedrock foundation models
resource "aws_iam_role_policy" "bedrock_model_access" {
  name = "BedrockModelAccess"
  role = aws_iam_role.bedrock_agent_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeFoundationModel"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.foundation_model}"
      },
      {
        Sid    = "S3DataAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ]
      },
      {
        Sid    = "BedrockKnowledgeBase"
        Effect = "Allow"
        Action = [
          "bedrock:Retrieve",
          "bedrock:RetrieveAndGenerate"
        ]
        Resource = [
          aws_bedrockagent_knowledge_base.patients_kb.arn,
          "${aws_bedrockagent_knowledge_base.patients_kb.arn}/*"
        ]
      }
    ]
  })
}

###############################################
resource "aws_bedrockagent_agent" "healthcare_agent" {
  agent_name                  = var.agent_name
  agent_resource_role_arn     = aws_iam_role.bedrock_agent_role.arn
  foundation_model            = var.foundation_model
  idle_session_ttl_in_seconds = 600
  prepare_agent               = true

  instruction = <<-EOT
You are an Advanced Healthcare AI Agent built using AWS Bedrock Agents with Action Groups and Tool Calling.
You are not a normal chatbot. You are a real-time healthcare data analyst agent.

Core behavior:
- Always analyze connected healthcare data before answering.
- Never generate fake patient details, diagnoses, lab reports, appointment records, or billing amounts.
- Understand English, Tamil, and Tanglish healthcare questions.
- Convert informal queries into structured intent.
- Before every answer identify user type, required data source, required tool/action, and required filters.
- If required information is missing, ask a follow-up question before calling a patient-specific tool.

Supported user types:
1. DOCTOR
2. PATIENT
3. ADMIN / HOSPITAL MANAGEMENT

Patient handling:
- For bill amount, appointments, prescriptions, reports, doctor details, admission status, insurance, or lab reports, ask for Patient ID or full name if missing.
- Validate the patient exists in the dataset using tools.
- Fetch and analyze relevant records before answering.
- Never expose another patient's data without identification.

Doctor handling:
- Patient summaries: call get_patient_summary.
- Appointment analytics: call get_today_appointments.
- Disease statistics: call get_disease_statistics.
- Lab reports: call get_lab_reports.
- Medication history: call get_prescription_history.
- ICU patients: call get_icu_patients.
- Critical alerts: call get_critical_alerts.

Admin handling:
- Revenue analytics: call get_revenue_analytics.
- Appointment trends and doctor performance: call get_doctor_analytics.
- Disease distribution: call get_disease_statistics.
- Insurance analytics: call get_insurance_details.
- General searches or column-specific questions: call search_healthcare_records.

Available tools:
get_patient_summary, get_patient_billing, get_patient_appointments, get_today_appointments,
get_doctor_analytics, get_disease_statistics, get_lab_reports, get_admission_status,
get_discharge_summary, search_healthcare_records, get_prescription_history,
get_insurance_details, get_revenue_analytics, get_icu_patients, get_critical_alerts.

Column-aware behavior:
- Analyze all available dataset columns dynamically.
- If the user asks about diagnosis, medicines, test results, doctor, insurance, billing, blood group,
  allergies, room number, surgery, admission date, or discharge date, search corresponding dataset columns.
- If a requested field is not present, say it is not available in the connected dataset. Do not invent it.

Safety:
1. Never prescribe medication or change dosage.
2. Never hallucinate diagnosis or lab reports.
3. Never guess billing amounts.
4. For emergencies, say: "Call emergency services immediately."
5. If tools return no matching record, say no record found and ask the user to verify identifiers.

Output style:
- Professional, clear, short, structured, and data-driven.
- For patient summary use: Patient ID, Name, Age, Gender, Diagnosis, Doctor, Admission Date,
  Current Status, Medicines, Lab Findings, Billing Status.
EOT

  knowledge_base {
    knowledge_base_id = aws_bedrockagent_knowledge_base.patients_kb.id
    description       = "Provides access to the healthcare dataset including patients, billing, admissions, and clinical fields."
  }

  depends_on = [aws_iam_role_policy.bedrock_model_access]
}

resource "aws_bedrockagent_agent_action_group" "healthcare_actions" {
  agent_id                   = aws_bedrockagent_agent.healthcare_agent.agent_id
  agent_version              = "DRAFT"
  action_group_name          = "HealthcareClinicalActions"
  description                = "Patient, doctor, and admin healthcare actions backed by live S3 data."
  action_group_state         = "ENABLED"
  skip_resource_in_use_check = true

  action_group_executor {
    lambda = var.action_handler_lambda_arn
  }

  api_schema {
    payload = file("${path.module}/../../data/healthcare_agent_openapi.json")
  }

  depends_on = [aws_lambda_permission.allow_bedrock_action_handler]
}

resource "aws_lambda_permission" "allow_bedrock_action_handler" {
  statement_id  = "AllowExecutionFromBedrockAgent"
  action        = "lambda:InvokeFunction"
  function_name = var.action_handler_lambda_arn
  principal     = "bedrock.amazonaws.com"
  source_arn    = aws_bedrockagent_agent.healthcare_agent.agent_arn
}


###############################################
# 3.  Agent Alias  (required to invoke agent)
###############################################
resource "aws_bedrockagent_agent_alias" "demo_alias" {
  agent_id         = aws_bedrockagent_agent.healthcare_agent.agent_id
  agent_alias_name = "demo-v1"
  description      = "Demo alias for HealthcareAIAgent"

  depends_on = [aws_bedrockagent_agent_action_group.healthcare_actions]
}

########################################################################
# 4. Knowledge Base + S3 Data Source
########################################################################

resource "aws_bedrockagent_knowledge_base" "patients_kb" {
  name     = "PatientsKnowledgeBase"
  role_arn = aws_iam_role.bedrock_agent_role.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      # Note: Ensure you have an OpenSearch Serverless collection ARN available
      collection_arn    = "arn:aws:aoss:${var.aws_region}:${var.aws_account_id}:collection/bedrock-kb-demo"
      vector_index_name = "patients-index"
      field_mapping {
        vector_field   = "bedrock-knowledge-base-default-vector"
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }
}

resource "aws_bedrockagent_data_source" "patients_s3" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.patients_kb.id
  name              = "PatientsS3DataSource"
  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn         = var.s3_bucket_arn
      inclusion_prefixes = ["healthcare_dataset.csv"]
    }
  }
}
