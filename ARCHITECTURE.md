# Architecture Decision Record — Capital Portfolio Intelligence Platform (CPIP)

## Overview

CPIP is an internal cloud platform built on AWS that deploys and operates event-driven microservices using ECS Fargate. The platform is validated end-to-end using a financial services reference application — a client portfolio system that processes real-time trades and market price updates.

**The platform is the product. The portfolio application is proof it works.**

---

## System Architecture

```
Internet
    │
    ▼
Application Load Balancer (public subnets, us-east-1a + us-east-1b)
    │
    ├── /trades*   → Trade Service (ECS Fargate, private subnet)
    ├── /prices*   → Market Data Service (ECS Fargate, private subnet)
    └── default    → Portfolio Service (ECS Fargate, private subnet)
                            │
                    ┌───────┴────────┐
                    ▼                ▼
              RDS PostgreSQL    SNS/SQS Event Bus
              (private subnet)
```

**Event Flow:**
```
Trade Service     → SNS: cpip-trade-events   → SQS: portfolio-updates-queue → Portfolio Service
Market Data Service → SNS: cpip-price-updates → SQS: portfolio-recalc-queue  → Portfolio Service
```

---

## Decision 1: ECS Fargate vs EKS

**Chose: ECS Fargate**

ECS Fargate removes all node management — no EC2 instances to patch, no node groups to scale, no control plane to operate. Tasks are the unit of deployment. IAM roles attach directly to tasks with no additional tooling required.

EKS would be the right choice when you need custom schedulers, multi-cloud portability, or complex networking with service meshes. For a team running AWS-native workloads with no multi-cloud requirement, ECS is operationally simpler with the same security posture.

Capital One's JD explicitly lists ECS — this aligns with their container orchestration standard.

---

## Decision 2: SQS/SNS vs Apache Kafka

**Chose: SQS/SNS**

SQS and SNS are fully managed — no brokers to operate, no ZooKeeper, no partition rebalancing. They scale to zero cost when idle and integrate natively with IAM for access control.

The SNS fan-out pattern (one topic, multiple SQS subscribers) gives loose coupling between publishers and consumers. The Trade Service publishes one event and has no knowledge of who consumes it.

Kafka would be the right choice when you need message replay beyond SQS's 14-day retention, complex stream processing with exactly-once semantics, or sub-10ms latency. For this workload, SQS's at-least-once delivery with idempotency keys at the application layer is sufficient.

**DLQ strategy:** Each queue has a dead letter queue with maxReceiveCount=3. Failed messages retry 3 times automatically via visibility timeout, then land in the DLQ. A CloudWatch alarm fires when DLQ depth > 0.

---

## Decision 3: RDS PostgreSQL vs DynamoDB

**Chose: RDS PostgreSQL**

Portfolio value calculation requires a JOIN across two tables:

```sql
SELECT SUM(h.shares * p.price)
FROM holdings h
JOIN prices p ON h.symbol = p.symbol
WHERE h.client_id = :client_id
```

This is a fundamentally relational query. Modelling this in DynamoDB would require denormalization — duplicating price data into every holdings record — which creates consistency problems when prices update.

DynamoDB would be the right choice for the trades table in isolation (single-key access by trade_id, high write throughput, no joins needed). In a production system at scale, trades would move to DynamoDB while portfolio calculations stay in PostgreSQL.

**Portfolio value is always computed at read time** — never cached — so it's always consistent with the latest prices.

---

## Decision 4: GitHub Actions vs Jenkins

**Chose: GitHub Actions**

GitHub Actions is co-located with the code — no separate CI server to maintain, no plugins to update, no agents to provision. OIDC authentication to AWS is native and requires zero long-lived credentials.

Jenkins would be the right choice in an enterprise environment with existing Jenkins infrastructure, complex plugin requirements, or on-premises build agents. The pipeline stages (test → build → push → deploy) map 1:1 to a Jenkinsfile — the concepts are identical.

**OIDC authentication:** GitHub Actions authenticates to AWS by exchanging a short-lived JWT for temporary STS credentials. No AWS access keys are stored anywhere. Credentials expire after 15 minutes automatically.

---

## Decision 5: Secrets Manager vs Parameter Store

**Chose: Secrets Manager**

Secrets Manager is purpose-built for credentials — it supports automatic rotation, has a dedicated audit trail in CloudTrail, and integrates directly with ECS task definitions via the `secrets` field. Credentials are injected at container startup by the ECS execution role, never appearing in task definition environment variables.

Parameter Store would be the right choice for non-secret configuration values (feature flags, service URLs) where cost sensitivity matters. Parameter Store is free for standard parameters; Secrets Manager costs $0.40/secret/month.

---

## Decision 6: Terraform Modules vs Inline Configuration

**Chose: Reusable Terraform Modules**

Each infrastructure concern (VPC, ECS, RDS, messaging, secrets) is encapsulated in its own module with a clear input/output interface. The `envs/dev` root module wires them together by passing outputs from one module as inputs to the next.

This means:
- Adding a staging environment is a new folder under `envs/` with different variable values — no module code changes
- Each module can be tested and versioned independently
- The dependency chain is explicit: VPC outputs feed RDS, ECS, and messaging

Inline configuration would be faster to write initially but becomes unmaintainable as environments multiply.

---

## Security Design

| Layer | Control | Reason |
|-------|---------|--------|
| Network | RDS in private subnets, no public IP | Database unreachable from internet |
| Network | ECS tasks in private subnets, ALB is only ingress | No direct inbound to containers |
| Network | Security groups: ALB → ECS → RDS chain | Each layer only accepts traffic from the layer above |
| IAM | Per-service ECS task roles | Compromised container can't access other services' resources |
| IAM | OIDC for CI/CD | Zero long-lived credentials in GitHub |
| Secrets | Secrets Manager + ECS secrets injection | Credentials never in code, logs, or task definitions |
| Container | ECR scan_on_push = true | Vulnerability scanning on every image push |
| State | S3 versioning + encryption + DynamoDB locking | State is recoverable, encrypted, and protected from concurrent writes |

---

## What I Would Add for Production

- **Route 53 + ACM** — custom domain with TLS termination at the ALB
- **ECS Service Auto Scaling** — target tracking on CPU utilisation, min 2 / max 10 tasks per service
- **Blue/green deployments** — ECS + CodeDeploy for zero-downtime production deploys
- **KMS encryption** — customer-managed keys for RDS and S3 instead of AWS-managed keys
- **Multi-environment promotion** — dev → staging → prod with manual approval gate before prod
- **VPC Endpoints** — keep ECR, S3, SQS, SNS traffic off the public internet entirely
- **Separate databases per service** — currently shared RDS for simplicity; production would give each service its own schema to eliminate coupling

---

## Failure Scenarios

### 1. Trade Service crashes mid-flight
Trade is in PENDING status in the database. SNS publish may or may not have occurred. On restart, the SQS consumer in Portfolio Service will either process the message (if SNS published successfully) or the trade stays PENDING. A sweeper job would re-publish stale PENDING trades older than N minutes.

### 2. Portfolio Service crashes while consuming SQS
The unprocessed message becomes visible again after the visibility timeout (30 seconds). It retries up to 3 times. After 3 failures it moves to the DLQ. The `cpip-queue-depth` alarm fires if the DLQ accumulates messages.

### 3. Duplicate trade message delivered by SQS
SQS guarantees at-least-once delivery — duplicates are possible. The `trade_id` UUID is the idempotency key. Trade Service checks for an existing record before inserting. Portfolio Service updates holdings using `ON CONFLICT DO UPDATE` — applying the same operation twice produces the same result.

### 4. RDS becomes unavailable
ECS health checks call `/health` on each service, which pings the database. Unhealthy tasks are replaced automatically. The ALB stops routing to unhealthy targets. Services reconnect with exponential backoff on startup.

### 5. SNS delivery fails
SNS retries with exponential backoff internally. If the SQS subscription endpoint is consistently unavailable, messages can be sent to an SNS dead-letter topic. SQS DLQs catch messages that couldn't be processed after delivery.

### 6. Invalid price update causes unexpected portfolio values
Market Data Service validates `price > 0` at the API boundary. All price updates are logged as structured JSON with symbol, price, and timestamp — full audit trail in CloudWatch. Portfolio value is computed live from the database, so correcting the price immediately corrects all portfolio values on the next read.
