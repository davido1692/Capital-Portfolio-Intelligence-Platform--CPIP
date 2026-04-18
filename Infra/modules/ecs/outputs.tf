output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "portfolio_service_name" {
  value = aws_ecs_service.portfolio.name
}

output "trade_service_name" {
  value = aws_ecs_service.trade.name
}

output "market_data_service_name" {
  value = aws_ecs_service.market_data.name
}
