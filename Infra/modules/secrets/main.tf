resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "${var.project}/${var.environment}/db-credentials"
  description = "RDS credentials for CPIP ${var.environment}"

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id

  secret_string = jsonencode({
    username = var.db_username
    password = var.db_password
  })
}
