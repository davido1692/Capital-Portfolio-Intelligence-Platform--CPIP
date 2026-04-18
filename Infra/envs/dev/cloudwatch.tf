# ── Metric Filters ──────────────────────────────────────────────────────────────
# Extract custom metrics from structured JSON logs

resource "aws_cloudwatch_log_metric_filter" "portfolio_recalc_duration" {
  name           = "portfolio-recalc-duration"
  log_group_name = "/cpip/portfolio-service"
  pattern        = "{ $.event = \"portfolio_recalculated\" }"

  metric_transformation {
    name      = "PortfolioRecalcDuration"
    namespace = "CPIP/Dev"
    value     = "$.duration_ms"
    unit      = "Milliseconds"
  }
}

resource "aws_cloudwatch_log_metric_filter" "trade_submitted" {
  name           = "trade-submitted-count"
  log_group_name = "/cpip/trade-service"
  pattern        = "{ $.event = \"trade_submitted\" }"

  metric_transformation {
    name      = "TradeSubmittedCount"
    namespace = "CPIP/Dev"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "trade_failed" {
  name           = "trade-failed-count"
  log_group_name = "/cpip/trade-service"
  pattern        = "{ $.status = \"FAILED\" }"

  metric_transformation {
    name      = "TradeFailedCount"
    namespace = "CPIP/Dev"
    value     = "1"
    unit      = "Count"
  }
}

# ── Alarms ───────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "portfolio_recalc_slow" {
  alarm_name          = "cpip-portfolio-recalc-slow"
  alarm_description   = "Portfolio recalculation averaging over 5 seconds"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "PortfolioRecalcDuration"
  namespace           = "CPIP/Dev"
  period              = 60
  statistic           = "Average"
  threshold           = 5000
  treat_missing_data  = "notBreaching"

  tags = {
    Project     = "cpip"
    Environment = "dev"
  }
}

resource "aws_cloudwatch_metric_alarm" "trade_failure_rate" {
  alarm_name          = "cpip-trade-failure-rate"
  alarm_description   = "Trade failure count exceeded threshold"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "TradeFailedCount"
  namespace           = "CPIP/Dev"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  tags = {
    Project     = "cpip"
    Environment = "dev"
  }
}

resource "aws_cloudwatch_metric_alarm" "queue_depth" {
  alarm_name          = "cpip-queue-depth"
  alarm_description   = "SQS portfolio-updates queue depth exceeded 100 messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 100
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = "cpip-dev-portfolio-updates-queue"
  }

  tags = {
    Project     = "cpip"
    Environment = "dev"
  }
}

# ── Dashboard ────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "CPIP-Dev"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Trade Submissions per Minute"
          period = 60
          stat   = "Sum"
          metrics = [["CPIP/Dev", "TradeSubmittedCount"]]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Portfolio Recalculation Latency (ms)"
          period = 60
          stat   = "Average"
          metrics = [["CPIP/Dev", "PortfolioRecalcDuration"]]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "SQS Queue Depth"
          period = 60
          stat   = "Maximum"
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "cpip-dev-portfolio-updates-queue"],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "cpip-dev-portfolio-recalc-queue"]
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Trade Failures"
          period = 300
          stat   = "Sum"
          metrics = [["CPIP/Dev", "TradeFailedCount"]]
        }
      }
    ]
  })
}
