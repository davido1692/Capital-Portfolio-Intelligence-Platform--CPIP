variable "project" {
  description = "Project name used for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "vpc_id" {
  description = "VPC ID from vpc module"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for ALB"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS tasks"
  type        = list(string)
}

variable "sg_alb_id" {
  description = "ALB security group ID"
  type        = string
}

variable "sg_ecs_id" {
  description = "ECS security group ID"
  type        = string
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

variable "database_url" {
  description = "PostgreSQL connection string"
  type        = string
  sensitive   = true
}

variable "trade_events_topic_arn" {
  description = "SNS topic ARN for trade events"
  type        = string
}

variable "price_updates_topic_arn" {
  description = "SNS topic ARN for price updates"
  type        = string
}

variable "portfolio_updates_queue_url" {
  description = "SQS queue URL for portfolio updates"
  type        = string
}

variable "portfolio_recalc_queue_url" {
  description = "SQS queue URL for portfolio recalculation"
  type        = string
}

variable "portfolio_updates_queue_arn" {
  description = "SQS queue ARN for portfolio updates"
  type        = string
}

variable "portfolio_recalc_queue_arn" {
  description = "SQS queue ARN for portfolio recalculation"
  type        = string
}

variable "db_secret_arn" {
  description = "Secrets Manager ARN for DB credentials"
  type        = string
}
