# Lab 9 — Spry core monthly cost comparison

I took the no-GCP-account route for Lab 9.

**Evidence status:** Hand-calculated estimates, not Google Cloud or AWS Pricing Calculator outputs and not a bill. Neither calculator was run; saved calculator estimates remain a submission gap. Use the inputs below to reproduce the estimates with the [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator) and [AWS Pricing Calculator](https://calculator.aws/). If a calculator does not model auto-pause, Firebase Hosting or account-level free usage, show that adjustment separately rather than entering a fake SKU or treating the estimate as a bill.

## Scope and inputs

- USD list rates, 730-hour month, no tax, promotional credits or discounts. Take the Lab 9 reference rates where supplied: AWS `us-east-1`, Google Cloud `us-central1`. The AWS column models the **course's Lab 4 Stage 2** layout for Spry's core: CloudFront/S3, Lambda and Aurora PostgreSQL Serverless v2. It does **not** price this fork's existing `eu-north-1` ECS/Fargate, ALB and RDS deployment, which has different idle costs. These are alternative core stacks, not the combined bill for running both at once.
- Same relational meetings workload on each side. One zonal Cloud SQL Enterprise `db-f1-micro` with 10 GB SSD; one Aurora Standard writer with compatible auto-pause, min 0/max 1 ACU, modeled at 0.5 ACU whenever awake. Assume 1 GB-month of Aurora storage and no extra billed backup storage on either side, no replicas, no NAT or provisioned API capacity. The Aurora charge grows if it needs more than 0.5 ACU or larger storage. Assume the database starts each active window once; five idle minutes per window before Aurora pauses, no persistent connections, keepalives or background jobs that block pausing. Nobody starts already paused; busy never pauses.
- Every active hour has 200 HTTP API calls, 250 ms of billable time per call, 4 KiB outbound API payload per call, and 10 MiB of static asset transfer across 500 static requests (365,000 static requests and about 7.13 GiB/month at busy). Model one Aurora storage I/O per API call on average as a budget input, not a conversion rule for SQL. “Busy” means continuous light student traffic, not saturation. No load test or measured utilization is implied.
- Cloud Run: 1 vCPU, 512 MiB, request-based, min 0. For compute budgeting count the full 250 ms per request without concurrency savings. Busy base usage: 146,000 requests, 36,500 vCPU-s, 18,250 GiB-s and ≈0.56 GiB API egress. The compute inputs are below 2M requests, 180,000 vCPU-s and 360,000 GiB-s per month; the corresponding excess rates are $0.40/1M requests, $0.000024/vCPU-s and $0.0000025/GiB-s. Assume startup/migrations and logging remain within quota headroom, and North American outbound traffic stays within 1 GiB/month. Lambda: 1 GiB, 36,500 GB-s in busy; assume the recurring Lambda allowances (1M requests and 400,000 GB-s/month, shared across eligible usage) are still available. No Lambda provisioned concurrency. Matching billable time is a scenario assumption, not a compute-equivalence claim.
- Assume unused quotas: Firebase Hosting ≤0.10 GB stored and ≤240 MiB/day at busy (below the lab's 10 GB/360 MB per day and below 10 GB/month); CloudFront Free flat-rate plan (including WAF, 1M requests, 100 GB transfer and 5 GB S3 storage credit), with ≤0.10 GB stored and CDN origin operations rounding to $0.00. AWS API transfer is within the applicable shared internet-egress allowance. Registry images retain 0.30 GB on either cloud; use ECR list storage price $0.10/GB-month without temporary trial eligibility and Artifact Registry's first 0.5 GB free. Assume one AWS Secrets Manager secret ($0.40/month) with at most 100 calls ($0.005/1,000 calls, or at most $0.0005 additional); one GCP active secret version and ≤1,000 accesses (6 versions and 10,000 accesses free). Model <0.5 GiB/month of logs, within recurring Cloud Logging and CloudWatch Logs allowances, and no paid retention/export. Free quotas may be shared with other workloads.
- Cognito stays on AWS and is unchanged on both sides; no incremental identity charge assumed for this small cohort. AWS weekly report, SES and Bedrock are outside the core comparison and do not run against the GCP dataset. No GCP substitutes for these are provisioned or modeled.

## Four profiles

Monthly USD, rounded after calculation. Primary GCP estimate leaves Cloud SQL running through the month while Cloud Run scales to zero.

| Piece / model | Nobody (0 h) | Class demos (10 × 2 h) | Office hours (8 h × 22 days) | Busy (730 h) |
| --- | ---: | ---: | ---: | ---: |
| API requests per cloud | 0 | 4,000 | 35,200 | 146,000 |
| Aurora awake hours | 0 | 20.83 | 177.83 | 730 |
| AWS frontend + CDN + HTTPS/WAF | $0.00 | $0.00 | $0.00 | $0.00 |
| AWS Lambda + function URL | $0.00 | $0.00 | $0.00 | $0.00 |
| AWS Aurora compute: awake hours × 0.5 ACU × $0.12/ACU-h | $0.00 | $1.25 | $10.67 | $43.80 |
| AWS Aurora storage: 1 GB × $0.10/GB-month | $0.10 | $0.10 | $0.10 | $0.10 |
| AWS Aurora I/O: storage ops × $0.20/1M | $0.00 | $0.00 | $0.01 | $0.03 |
| AWS ECR + secret + logs | $0.43 | $0.43 | $0.43 | $0.43 |
| **AWS total** | **$0.53** | **$1.78** | **$11.21** | **$44.36** |
| GCP Firebase Hosting + CDN + HTTPS | $0.00 | $0.00 | $0.00 | $0.00 |
| GCP Cloud Run + API egress | $0.00 | $0.00 | $0.00 | $0.00 |
| GCP Cloud SQL compute: 730 h × $0.0105/h | $7.67 | $7.67 | $7.67 | $7.67 |
| GCP Cloud SQL SSD: 10 GB × $0.17/GB-month | $1.70 | $1.70 | $1.70 | $1.70 |
| GCP Artifact Registry + secret + logs | $0.00 | $0.00 | $0.00 | $0.00 |
| **GCP total (Cloud SQL always on)** | **$9.37** | **$9.37** | **$9.37** | **$9.37** |
| **Cheaper (always-on Cloud SQL baseline)** | **AWS** | **AWS** | **GCP** | **GCP** |

The line that flips the comparison is **database compute**. Aurora pauses, so its compute is $0 for nobody and $1.25 for demos. At office hours and busy, its $10.67/$43.80 exceeds the same $7.67 Cloud SQL compute line. Ignoring the small I/O line, the modeled crossover is `(9.365 − 0.53) / (0.5 × 0.12)` ≈ **147 awake hours/month**, not 147 hours of human attendance. The lab's ≈$0.30 idle AWS example is not an input to this table: this budget explicitly carries a full-price Secrets Manager secret plus ECR and storage.

### What stopping Cloud SQL buys

This is an availability trade-off, not automatic pause. Assume operator starts the database five minutes before each session; let `h` be its running hours (0, 20.83, 177.83, 730 respectively). Compute/storage subtotal is `$1.70 + $0.0105 × h`. If the public IPv4 remains assigned when stopped, add `$0.01 × (730 − h)` for idle IPv4 ([Cloud SQL pricing](https://cloud.google.com/sql/pricing), Iowa storage/networking). The no-idle-IP scenario needs a different IP/network setup or the address removed; it does not budget the cost of the private network path or IP reconfiguration. Backups, if retained and billable, add separately.

| Cloud SQL operated on a schedule | Nobody | Class demos | Office hours | Busy |
| --- | ---: | ---: | ---: | ---: |
| GCP core with no billed idle IPv4 | $1.70 | $1.92 | $3.57 | $9.37 |
| GCP core with public IPv4 retained | $9.00 | $9.01 | $9.09 | $9.37 |

The profile winners are unchanged under either sensitivity: AWS for nobody/demos, GCP for office/busy. The GCP trap is assuming **Cloud Run scaling to zero also stops Cloud SQL**. It doesn't: forgetting Cloud SQL leaves about $9.37/month here, and stopping it with public IPv4 retained still leaves about $9/month. Cloud Run min instances or switching to instance-based billing can also create costs the request-based model omits. Conversely, if connections prevent Aurora pausing even in the nobody profile, Aurora adds `$0.12 × 0.5 × 730 = $43.80` of compute. Firestore is not the costed deployment: its lack of an idle instance charge comes with a relational data/model rewrite (see [ADR 0008](../../adr/0008-gcp.md)).

## Rate and quota references

- Google: [Cloud SQL rates](https://cloud.google.com/sql/pricing), [Cloud Run billing and free quotas](https://cloud.google.com/run/pricing), [Firebase Hosting quotas](https://firebase.google.com/docs/hosting/usage-quotas-pricing), [Artifact Registry](https://cloud.google.com/artifact-registry/pricing), [Secret Manager](https://cloud.google.com/secret-manager/pricing), [Cloud Logging](https://cloud.google.com/stackdriver/pricing).
- AWS: [Aurora prices](https://aws.amazon.com/rds/aurora/pricing/) and [auto-pause requirements](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html), [CloudFront plans](https://aws.amazon.com/cloudfront/pricing/), [Lambda](https://aws.amazon.com/lambda/pricing/), [ECR](https://aws.amazon.com/ecr/pricing/), [Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/), [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/).
