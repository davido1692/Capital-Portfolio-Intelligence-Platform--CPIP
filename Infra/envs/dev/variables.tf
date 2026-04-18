variable "aws_region" {
  default = "us-east-1"
}

variable "db_password" {
  description = "RDS master password — pass via TF_VAR_db_password environment variable"
  type        = string
  sensitive   = true
}

variable "portfolio_image" {
  description = "ECR image URI for portfolio service"
  type        = string
}

variable "trade_image" {
  description = "ECR image URI for trade service"
  type        = string
}

variable "market_data_image" {
  description = "ECR image URI for market data service"
  type        = string
}
