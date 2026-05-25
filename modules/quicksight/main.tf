########################################################################
# modules/quicksight/main.tf
# QuickSight: healthcare_dataset.csv DataSource -> DataSet -> Dashboard
########################################################################

resource "aws_iam_role" "quicksight_s3_role" {
  name = "QuickSightS3AccessRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "quicksight.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "quicksight_s3_policy" {
  name = "QuickSightS3Policy"
  role = aws_iam_role.quicksight_s3_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListAllMyBuckets"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_quicksight_data_source" "patients_s3" {
  data_source_id = "healthcare-dataset-csv"
  name           = "healthcare_dataset.csv"
  aws_account_id = var.aws_account_id
  type           = "S3"

  parameters {
    s3 {
      manifest_file_location {
        bucket = var.s3_bucket_name
        key    = var.manifest_key
      }
    }
  }

  permission {
    actions = [
      "quicksight:DescribeDataSource",
      "quicksight:DescribeDataSourcePermissions",
      "quicksight:PassDataSource",
      "quicksight:UpdateDataSource",
      "quicksight:DeleteDataSource",
      "quicksight:UpdateDataSourcePermissions"
    ]
    principal = "arn:aws:quicksight:${var.aws_region}:${var.aws_account_id}:user/default/${var.quicksight_user}"
  }

  ssl_properties {
    disable_ssl = false
  }

  depends_on = [aws_iam_role_policy.quicksight_s3_policy]
}

resource "aws_quicksight_data_set" "patients_dataset" {
  data_set_id    = "patients-healthcare-dataset"
  name           = var.dataset_name
  aws_account_id = var.aws_account_id
  import_mode    = "SPICE"

  physical_table_map {
    physical_table_map_id = "patients-table"

    s3_source {
      data_source_arn = aws_quicksight_data_source.patients_s3.arn

      input_columns {
        name = "Name"
        type = "STRING"
      }
      input_columns {
        name = "Age"
        type = "STRING"
      }
      input_columns {
        name = "Gender"
        type = "STRING"
      }
      input_columns {
        name = "Blood Type"
        type = "STRING"
      }
      input_columns {
        name = "Medical Condition"
        type = "STRING"
      }
      input_columns {
        name = "Date of Admission"
        type = "STRING"
      }
      input_columns {
        name = "Doctor"
        type = "STRING"
      }
      input_columns {
        name = "Hospital"
        type = "STRING"
      }
      input_columns {
        name = "Insurance Provider"
        type = "STRING"
      }
      input_columns {
        name = "Billing Amount"
        type = "STRING"
      }
      input_columns {
        name = "Room Number"
        type = "STRING"
      }
      input_columns {
        name = "Admission Type"
        type = "STRING"
      }
      input_columns {
        name = "Discharge Date"
        type = "STRING"
      }
      input_columns {
        name = "Medication"
        type = "STRING"
      }
      input_columns {
        name = "Test Results"
        type = "STRING"
      }

      upload_settings {
        format = "CSV"
      }
    }
  }

  logical_table_map {
    logical_table_map_id = "patients-logical"
    alias                = "Healthcare Records"

    source {
      physical_table_id = "patients-table"
    }

    data_transforms {
      create_columns_operation {
        columns {
          column_id   = "AGE_NUM"
          column_name = "AGE_NUM"
          expression  = "parseDecimal({Age})"
        }

        columns {
          column_id   = "BILLING_AMOUNT_NUM"
          column_name = "BILLING_AMOUNT_NUM"
          expression  = "parseDecimal({Billing Amount})"
        }
      }
    }
  }

  permissions {
    actions = [
      "quicksight:DescribeDataSet",
      "quicksight:DescribeDataSetPermissions",
      "quicksight:PassDataSet",
      "quicksight:DescribeIngestion",
      "quicksight:ListIngestions",
      "quicksight:UpdateDataSet",
      "quicksight:DeleteDataSet",
      "quicksight:CreateIngestion",
      "quicksight:CancelIngestion",
      "quicksight:UpdateDataSetPermissions"
    ]
    principal = "arn:aws:quicksight:${var.aws_region}:${var.aws_account_id}:user/default/${var.quicksight_user}"
  }

  depends_on = [aws_quicksight_data_source.patients_s3]
}

resource "aws_quicksight_dashboard" "healthcare_dashboard" {
  dashboard_id   = "Healthcare dashboard"
  name           = "Healthcare AI Insights Dashboard"
  aws_account_id = var.aws_account_id

  version_description = "v2 - healthcare_dataset.csv analytics"

  definition {
    data_set_identifiers_declarations {
      identifier   = "PatientsDataset"
      data_set_arn = aws_quicksight_data_set.patients_dataset.arn
    }

    sheets {
      sheet_id = "overview-sheet"
      name     = "Healthcare Overview"

      visuals {
        pie_chart_visual {
          visual_id = "gender-pie"
          title {
            format_text {
              plain_text = "Gender Distribution"
            }
          }

          chart_configuration {
            field_wells {
              pie_chart_aggregated_field_wells {
                category {
                  categorical_dimension_field {
                    field_id = "gender-field"
                    column {
                      column_name         = "Gender"
                      data_set_identifier = "PatientsDataset"
                    }
                  }
                }
                values {
                  categorical_measure_field {
                    field_id             = "gender-count"
                    aggregation_function = "COUNT"
                    column {
                      column_name         = "Gender"
                      data_set_identifier = "PatientsDataset"
                    }
                  }
                }
              }
            }
          }
        }
      }

      visuals {
        bar_chart_visual {
          visual_id = "condition-bar"
          title {
            format_text {
              plain_text = "Patient Count by Medical Condition"
            }
          }

          chart_configuration {
            field_wells {
              bar_chart_aggregated_field_wells {
                category {
                  categorical_dimension_field {
                    field_id = "condition-field"
                    column {
                      column_name         = "Medical Condition"
                      data_set_identifier = "PatientsDataset"
                    }
                  }
                }
                values {
                  categorical_measure_field {
                    field_id             = "condition-count"
                    aggregation_function = "COUNT"
                    column {
                      column_name         = "Medical Condition"
                      data_set_identifier = "PatientsDataset"
                    }
                  }
                }
              }
            }
          }
        }
      }

      visuals {
        kpi_visual {
          visual_id = "billing-kpi"
          title {
            format_text {
              plain_text = "Average Billing Amount"
            }
          }

          chart_configuration {
            field_wells {
              values {
                numerical_measure_field {
                  field_id = "avg-billing"
                  aggregation_function {
                    simple_numerical_aggregation = "AVERAGE"
                  }
                  column {
                    column_name         = "BILLING_AMOUNT_NUM"
                    data_set_identifier = "PatientsDataset"
                  }
                }
              }
            }
          }
        }
      }

      visuals {
        bar_chart_visual {
          visual_id = "insurance-billing-bar"
          title {
            format_text {
              plain_text = "Billing Amount by Insurance Provider"
            }
          }

          chart_configuration {
            field_wells {
              bar_chart_aggregated_field_wells {
                category {
                  categorical_dimension_field {
                    field_id = "insurance-field"
                    column {
                      column_name         = "Insurance Provider"
                      data_set_identifier = "PatientsDataset"
                    }
                  }
                }
                values {
                  numerical_measure_field {
                    field_id = "billing-sum"
                    aggregation_function {
                      simple_numerical_aggregation = "SUM"
                    }
                    column {
                      column_name         = "BILLING_AMOUNT_NUM"
                      data_set_identifier = "PatientsDataset"
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }

  permissions {
    actions = [
      "quicksight:DescribeDashboard",
      "quicksight:ListDashboardVersions",
      "quicksight:UpdateDashboardPermissions",
      "quicksight:QueryDashboard",
      "quicksight:UpdateDashboard",
      "quicksight:DeleteDashboard",
      "quicksight:UpdateDashboardPublishedVersion",
      "quicksight:DescribeDashboardPermissions"
    ]
    principal = "arn:aws:quicksight:${var.aws_region}:${var.aws_account_id}:user/default/${var.quicksight_user}"
  }

  depends_on = [aws_quicksight_data_set.patients_dataset]
}
