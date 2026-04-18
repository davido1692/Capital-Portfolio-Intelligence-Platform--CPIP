variable "project" {
  description = "Project name used for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "db_username" {
  description = "Database username"
  type        = string
  default     = "cpip"
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}
