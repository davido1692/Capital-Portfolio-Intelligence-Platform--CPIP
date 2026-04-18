resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-${var.environment}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name        = "${var.project}-${var.environment}-db-subnet-group"
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_db_parameter_group" "main" {
  name   = "${var.project}-${var.environment}-pg15"
  family = "postgres15"

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_db_instance" "main" {
  identifier        = "${var.project}-${var.environment}"
  engine            = "postgres"
  engine_version    = "15"
  instance_class    = var.instance_class
  db_name           = "cpip"
  username          = var.db_username
  password          = var.db_password
  port              = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.sg_rds_id]
  parameter_group_name   = aws_db_parameter_group.main.name

  allocated_storage     = 20
  storage_type          = "gp2"
  storage_encrypted     = true

  # No public access — private subnets only
  publicly_accessible = false

  backup_retention_period = 7
  skip_final_snapshot     = true

  tags = {
    Name        = "${var.project}-${var.environment}-rds"
    Project     = var.project
    Environment = var.environment
  }
}
