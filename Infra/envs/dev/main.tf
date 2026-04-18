terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  project     = "cpip"
  environment = "dev"
}

# ── VPC ─────────────────────────────────────────────────────────────────────────

module "vpc" {
  source      = "../../modules/vpc"
  project     = local.project
  environment = local.environment
}

# ── ECR ─────────────────────────────────────────────────────────────────────────

module "ecr" {
  source      = "../../modules/ecr"
  project     = local.project
  environment = local.environment
}

# ── Secrets ──────────────────────────────────────────────────────────────────────

module "secrets" {
  source      = "../../modules/secrets"
  project     = local.project
  environment = local.environment
  db_password = var.db_password
}

# ── RDS ─────────────────────────────────────────────────────────────────────────

module "rds" {
  source             = "../../modules/rds"
  project            = local.project
  environment        = local.environment
  private_subnet_ids = module.vpc.private_subnet_ids
  sg_rds_id          = module.vpc.sg_rds_id
  db_password        = var.db_password
}

# ── Messaging ────────────────────────────────────────────────────────────────────

module "messaging" {
  source      = "../../modules/messaging"
  project     = local.project
  environment = local.environment
}

# ── ECS ─────────────────────────────────────────────────────────────────────────

module "ecs" {
  source      = "../../modules/ecs"
  project     = local.project
  environment = local.environment
  aws_region  = var.aws_region

  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids
  sg_alb_id          = module.vpc.sg_alb_id
  sg_ecs_id          = module.vpc.sg_ecs_id

  portfolio_image   = var.portfolio_image
  trade_image       = var.trade_image
  market_data_image = var.market_data_image

  database_url = "postgresql://${module.rds.db_endpoint}/${module.rds.db_name}"

  trade_events_topic_arn      = module.messaging.trade_events_topic_arn
  price_updates_topic_arn     = module.messaging.price_updates_topic_arn
  portfolio_updates_queue_url = module.messaging.portfolio_updates_queue_url
  portfolio_recalc_queue_url  = module.messaging.portfolio_recalc_queue_url
  portfolio_updates_queue_arn = "arn:aws:sqs:${var.aws_region}:*:cpip-dev-portfolio-updates-queue"
  portfolio_recalc_queue_arn  = "arn:aws:sqs:${var.aws_region}:*:cpip-dev-portfolio-recalc-queue"

  db_secret_arn = module.secrets.db_secret_arn
}
