data "aws_caller_identity" "current" {}

# ── ECS Cluster ─────────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${var.project}-${var.environment}"

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# ── CloudWatch Log Groups ───────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "services" {
  for_each          = toset(["portfolio-service", "trade-service", "market-data-service"])
  name              = "/${var.project}/${each.key}"
  retention_in_days = 30

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# ── IAM: Shared Task Execution Role ────────────────────────────────────────────

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project}-${var.environment}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name = "secrets-manager-read"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [var.db_secret_arn]
    }]
  })
}

# ── IAM: Per-Service Task Roles (least privilege) ───────────────────────────────

resource "aws_iam_role" "portfolio_task" {
  name = "${var.project}-${var.environment}-portfolio-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "portfolio_task" {
  name = "sqs-consume"
  role = aws_iam_role.portfolio_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ]
      Resource = [
        var.portfolio_updates_queue_arn,
        var.portfolio_recalc_queue_arn
      ]
    }]
  })
}

resource "aws_iam_role" "trade_task" {
  name = "${var.project}-${var.environment}-trade-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "trade_task" {
  name = "sns-publish"
  role = aws_iam_role.trade_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = [var.trade_events_topic_arn]
    }]
  })
}

resource "aws_iam_role" "market_data_task" {
  name = "${var.project}-${var.environment}-market-data-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "market_data_task" {
  name = "sns-publish"
  role = aws_iam_role.market_data_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = [var.price_updates_topic_arn]
    }]
  })
}

# ── ALB ─────────────────────────────────────────────────────────────────────────

resource "aws_lb" "main" {
  name               = "${var.project}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.sg_alb_id]
  subnets            = var.public_subnet_ids

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_lb_target_group" "portfolio" {
  name        = "${var.project}-${var.environment}-portfolio-tg"
  port        = 5001
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}

resource "aws_lb_target_group" "trade" {
  name        = "${var.project}-${var.environment}-trade-tg"
  port        = 5002
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}

resource "aws_lb_target_group" "market_data" {
  name        = "${var.project}-${var.environment}-market-tg"
  port        = 5003
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}

resource "aws_lb_listener" "main" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.portfolio.arn
  }
}

resource "aws_lb_listener_rule" "trade" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.trade.arn
  }

  condition {
    path_pattern {
      values = ["/trades*"]
    }
  }
}

resource "aws_lb_listener_rule" "market_data" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.market_data.arn
  }

  condition {
    path_pattern {
      values = ["/prices*"]
    }
  }
}

# ── ECS Task Definitions ────────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "portfolio" {
  family                   = "${var.project}-${var.environment}-portfolio"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.portfolio_task.arn

  container_definitions = jsonencode([{
    name  = "portfolio-service"
    image = var.portfolio_image

    portMappings = [{
      containerPort = 5001
      protocol      = "tcp"
    }]

    environment = [
      { name = "AWS_REGION", value = var.aws_region },
      { name = "PORTFOLIO_UPDATES_QUEUE_URL", value = var.portfolio_updates_queue_url },
      { name = "PORTFOLIO_RECALC_QUEUE_URL", value = var.portfolio_recalc_queue_url }
    ]

    secrets = [{
      name      = "DATABASE_URL"
      valueFrom = "${var.db_secret_arn}:DATABASE_URL::"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/${var.project}/portfolio-service"
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "trade" {
  family                   = "${var.project}-${var.environment}-trade"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.trade_task.arn

  container_definitions = jsonencode([{
    name  = "trade-service"
    image = var.trade_image

    portMappings = [{
      containerPort = 5002
      protocol      = "tcp"
    }]

    environment = [
      { name = "AWS_REGION", value = var.aws_region },
      { name = "TRADE_EVENTS_TOPIC_ARN", value = var.trade_events_topic_arn }
    ]

    secrets = [{
      name      = "DATABASE_URL"
      valueFrom = "${var.db_secret_arn}:DATABASE_URL::"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/${var.project}/trade-service"
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "market_data" {
  family                   = "${var.project}-${var.environment}-market-data"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.market_data_task.arn

  container_definitions = jsonencode([{
    name  = "market-data-service"
    image = var.market_data_image

    portMappings = [{
      containerPort = 5003
      protocol      = "tcp"
    }]

    environment = [
      { name = "AWS_REGION", value = var.aws_region },
      { name = "PRICE_UPDATES_TOPIC_ARN", value = var.price_updates_topic_arn },
      { name = "MOCK_PRICES_ENABLED", value = "true" }
    ]

    secrets = [{
      name      = "DATABASE_URL"
      valueFrom = "${var.db_secret_arn}:DATABASE_URL::"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/${var.project}/market-data-service"
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

# ── ECS Services ────────────────────────────────────────────────────────────────

resource "aws_ecs_service" "portfolio" {
  name            = "${var.project}-${var.environment}-portfolio"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.portfolio.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.sg_ecs_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.portfolio.arn
    container_name   = "portfolio-service"
    container_port   = 5001
  }

  depends_on = [aws_lb_listener.main]
}

resource "aws_ecs_service" "trade" {
  name            = "${var.project}-${var.environment}-trade"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.trade.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.sg_ecs_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.trade.arn
    container_name   = "trade-service"
    container_port   = 5002
  }

  depends_on = [aws_lb_listener.main]
}

resource "aws_ecs_service" "market_data" {
  name            = "${var.project}-${var.environment}-market-data"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.market_data.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.sg_ecs_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.market_data.arn
    container_name   = "market-data-service"
    container_port   = 5003
  }

  depends_on = [aws_lb_listener.main]
}
