output "alb_dns_name" {
  description = "ALB DNS name — use this to access the API"
  value       = module.ecs.alb_dns_name
}

output "ecr_repository_urls" {
  description = "ECR repository URLs for pushing Docker images"
  value       = module.ecr.repository_urls
}

output "db_endpoint" {
  description = "RDS endpoint"
  value       = module.rds.db_endpoint
}

output "ecs_cluster_name" {
  value = module.ecs.ecs_cluster_name
}
