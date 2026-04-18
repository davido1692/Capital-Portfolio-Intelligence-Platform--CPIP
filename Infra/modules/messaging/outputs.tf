output "trade_events_topic_arn" {
  value = aws_sns_topic.trade_events.arn
}

output "price_updates_topic_arn" {
  value = aws_sns_topic.price_updates.arn
}

output "portfolio_updates_queue_url" {
  value = aws_sqs_queue.portfolio_updates.id
}

output "portfolio_recalc_queue_url" {
  value = aws_sqs_queue.portfolio_recalc.id
}

output "portfolio_updates_dlq_arn" {
  value = aws_sqs_queue.portfolio_updates_dlq.arn
}

output "portfolio_recalc_dlq_arn" {
  value = aws_sqs_queue.portfolio_recalc_dlq.arn
}
