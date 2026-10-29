# Spry — C4 level 2: agenda parser

This diagram describes the implemented Lab 4/5 deployment and the proposed Lab 6 AI path. The parse Lambda has no VPC/database access; the model does not write. The existing Spry API uses ECS Fargate and PostgreSQL RDS, not Aurora. Both stacks are in `eu-north-1`; the isolated Bedrock parser and Lambda image registry are in `us-east-1`.

```mermaid
C4Container
    title Spry — Paste an agenda and save (C4 level 2)
    Person(user, "User", "Signs in, pastes text, reviews and edits suggestions")
    System_Ext(cognito, "Amazon Cognito", "OIDC login, access tokens, JWKS")
    System_Ext(bedrock, "Amazon Bedrock", "Foundation model via Converse or Messages")
    System_Boundary(spry, "Spry") {
        Container(web, "Web SPA", "S3 + CloudFront, React", "Meeting page, editable agenda form, progress and cancel")
        Container(parser, "Agenda parser", "Lambda container, Function URL, us-east-1", "Validates Cognito JWT, bounds input, requests structured suggestion; no VPC")
        Container(api, "Main API", "FastAPI on ECS Fargate, eu-north-1", "Authoritative authenticated validation and agenda write")
        ContainerDb(db, "Meetings database", "Amazon RDS PostgreSQL, private subnets", "Meetings, reviewed agendas and optional AI provenance")
        Container(logs, "Parser logs and budget", "CloudWatch + AWS Budgets", "Tokens, latency and estimated model cost; $5 alarm is not a hard spending cap")
    }
    Rel(user, web, "Sign in, paste, review, edit, Save", "HTTPS")
    Rel(web, cognito, "Sign-in and token refresh", "OIDC/HTTPS")
    Rel(web, parser, "Parse text + local date/timezone, Bearer access token", "HTTPS POST")
    Rel(parser, cognito, "Fetch trusted pool signing keys", "JWKS/HTTPS")
    Rel(parser, bedrock, "Request one structured record_agenda tool response", "HTTPS")
    Rel(parser, logs, "Log usage, latency, estimated cost; no pasted text", "AWS API")
    Rel(web, api, "Save reviewed form + original suggestion/model/version", "HTTPS POST /api/meetings/{id}/agenda")
    Rel(api, cognito, "Verify signed access token", "JWKS/HTTPS")
    Rel(api, db, "Validated agenda upsert", "TLS PostgreSQL")
```

The public Function URL is authenticated inside Lambda; CORS is a browser restriction, **not** an authorization or rate-limit mechanism. Reserved concurrency is a coarse bill/abuse guard, not a per-user quota. Invalid or unavailable model responses do not block manual agenda entry. The $5 AWS Budget is an alarm, not a cap: an account with many valid users can still create spend before notification. See [ADR 0006](adr/0006-llm-agenda-parsing.md).
