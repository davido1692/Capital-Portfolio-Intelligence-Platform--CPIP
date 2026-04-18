# ── Dead Letter Queues ──────────────────────────────────────────────────────────

resource "aws_sqs_queue" "portfolio_updates_dlq" {
  name                      = "${var.project}-${var.environment}-portfolio-updates-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_sqs_queue" "portfolio_recalc_dlq" {
  name                      = "${var.project}-${var.environment}-portfolio-recalc-dlq"
  message_retention_seconds = 1209600

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# ── Main Queues ─────────────────────────────────────────────────────────────────

resource "aws_sqs_queue" "portfolio_updates" {
  name                       = "${var.project}-${var.environment}-portfolio-updates-queue"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400 # 1 day

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.portfolio_updates_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_sqs_queue" "portfolio_recalc" {
  name                       = "${var.project}-${var.environment}-portfolio-recalc-queue"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.portfolio_recalc_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# ── SNS Topics ──────────────────────────────────────────────────────────────────

resource "aws_sns_topic" "trade_events" {
  name = "${var.project}-${var.environment}-trade-events"

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_sns_topic" "price_updates" {
  name = "${var.project}-${var.environment}-price-updates"

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# ── SNS → SQS Subscriptions ─────────────────────────────────────────────────────

resource "aws_sns_topic_subscription" "trade_events_to_portfolio_updates" {
  topic_arn = aws_sns_topic.trade_events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.portfolio_updates.arn
}

resource "aws_sns_topic_subscription" "price_updates_to_portfolio_recalc" {
  topic_arn = aws_sns_topic.price_updates.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.portfolio_recalc.arn
}

# ── SQS Queue Policies (allow SNS to send to queues) ───────────────────────────

resource "aws_sqs_queue_policy" "portfolio_updates" {
  queue_url = aws_sqs_queue.portfolio_updates.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "sns.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.portfolio_updates.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.trade_events.arn
          }
        }
      }
    ]
  })
}

resource "aws_sqs_queue_policy" "portfolio_recalc" {
  queue_url = aws_sqs_queue.portfolio_recalc.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "sns.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.portfolio_recalc.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.price_updates.arn
          }
        }
      }
    ]
  })
}
