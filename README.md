# Spry

Official public course fork: [mandziuk911/spry-lab](https://github.com/mandziuk911/spry-lab), forked from [dobosevych/OneTwoThree](https://github.com/dobosevych/OneTwoThree), preserving its history. The earlier private `mandziuk911/spry` repository remains a backup. The reviewed structure and API contract live in [PROJECT.md](PROJECT.md).

## Local startup

Install and start Docker Desktop, then from the repository root:

```bash
docker compose up --build
```

No host Python/Node, environment-file copy or manual migration is required. After the first build, `docker compose up` starts the same stack.

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- API docs: http://localhost:8000/api/docs
- Readiness: http://localhost:8000/api/health

Create a meeting with title, start, end and attendee count. Reload the page: it remains saved. Status follows the live browser clock: **Scheduled** (gray) before the start, **In progress** (green) between start and end, and **Finished** (gray) after the end. One hour after its end, a meeting hides from the default list and sidebar counts, but is **not deleted** and remains available through the API. Status updates every second and when returning to the tab; no separate calendar integration or background database job is involved. Use a meeting's Delete control and confirm to permanently remove it; cancellation makes no request. An empty database has no sample meetings.

The page uses a retro 2000s desktop/web style: glossy title bars, beveled controls and colorful appointment panels. This is a user-requested redesign, not a claim of matching the missing lab reference screenshots.

## Structure

- `back/`: FastAPI HTTP routers, Pydantic contracts, service logic, SQLAlchemy model, Alembic migrations and tests.
- `front/`: one React/Vite page, Tailwind and committed shadcn/ui primitives.
- `compose.yaml`: PostgreSQL, backend and frontend; health-based dependency ordering and persistent `pgdata` volume.
- `.github/workflows/`: automated quality checks.
- `infra/` and `Makefile`: reviewed Free-plan ECS/ALB/RDS and private S3/CloudFront configuration plus shared deploy commands. Obsolete Lambda/Cognito/domain recipes are removed. Cloud usage consumes credits.

The first three migration files are preserved from the course repository. A forward migration adapts their schema to the minimal slice. Migrations execute at container startup before the API serves requests, never during image build. Review destructive migrations before using valuable data; see the new migration's downgrade warning.

## Contract

`GET /api/meetings` returns an ordered JSON array. `POST /api/meetings` accepts exactly `title`, `starts_at`, `ends_at`, `attendee_count` and returns those fields plus a UUID `id` with HTTP 201. Dates require a timezone and responses use UTC. End must follow start; title must contain 1–200 trimmed characters; count must be a nonnegative integer. Invalid requests return 422. Database failures return 503.

`DELETE /api/meetings/{meeting_id}` permanently deletes one meeting by UUID and returns HTTP 204 with no body. A missing/already-deleted UUID returns 404 (`Meeting not found`); malformed UUID returns 422; database failures return 503. The UI confirms before deleting, prevents duplicate requests and keeps the meeting visible if deletion fails. An already-deleted meeting is removed from a stale local list with an explicit message.

**No accounts or author protection:** anyone with API access can delete any meeting. This is the user's requested fallback, not ownership enforcement. Do not use the workspace for sensitive shared data or expose it publicly without reviewing authentication/access controls. Participant management, editing and analytics remain out of scope.

## Operations and troubleshooting

```bash
docker compose ps
docker compose logs backend
docker compose down                  # preserves meetings
docker compose up --build            # rebuild after source changes
```

`docker compose down -v` deliberately destroys database data. There are no source bind mounts. Port conflicts require freeing ports 8000/5173 or explicitly changing Compose and matching frontend/CORS URLs together.

Database readiness uses pg_isready; the backend waits for it, migrates, and reports healthy only when it can query the database. The frontend waits for backend health. If PostgreSQL later disappears, clients receive visible errors; startup ordering does not guarantee permanent availability.

## Development versus production

The `spry` development credentials, Vite server, local CORS origin and published API port are for your laptop only. PostgreSQL is not published to the host. VITE settings are public browser configuration, never secrets. Optional `.env` overrides are ignored by Git. Use AWS CLI profiles locally and OIDC for CI, not committed access keys.

## AWS deployment (Free-plan lab/demo)

Prerequisites: Docker, Python 3, current AWS CLI, a clean committed checkout and temporary credentials:

```bash
aws login --profile spry --region eu-north-1
make aws-check
make deploy-backend
make deploy-frontend
make aws-outputs
```

The tooling refuses another account, root/IAM-user credentials, non-ACTIVE/non-Free plans or fewer than $20 remaining credits. It does not upgrade the account, purchase domains or load AWS keys from `.env`. A temporary Free-plan credit balance is not permanent free hosting; ALB, public IPv4, Fargate, RDS, secrets, storage and logs continuously consume credits.

CloudFront's default HTTPS hostname serves frontend and `/api` on the same origin. Its ALB origin uses HTTP: this is not end-to-end TLS and does not fulfill the lab's custom-domain requirement. S3 and PostgreSQL are private; ALB accepts CloudFront-origin traffic plus a secret header, and tasks accept only ALB traffic. Local database data is never uploaded. This unauthenticated production workspace is for disposable lab data only.

The backend uses Linux ARM64 SHA-tagged immutable ECR images and Secrets Manager DATABASE_URL injection, with PostgreSQL TLS. Production RDS pins available PostgreSQL 16.15; local Docker remains 16.8. Deployment first pauses the demo service, runs one Alembic task, checks its exit code, then enables the service and waits for stability. Failure stops deployment without deleting protected database data; recover explicitly after inspecting errors. This demo workflow is not zero-downtime deployment. No automatic irreversible migration downgrade is attempted.

Frontend builds on pinned Node 24.0.0 with `VITE_API_URL=/`. Hashed assets upload before `index.html`; older assets remain for rollback. CloudFront invalidations are awaited. Private origin-token/deployment state is stored outside Git in `~/.local/state/spry-aws/`; never publish the origin-token file.

Quality CI runs without AWS credentials. A separate main-only workflow waits for all quality checks, checks out their exact SHA, obtains OIDC temporary credentials via `aws-actions/configure-aws-credentials@v4`, and invokes the same Makefile targets. It does not cancel running migrations. **Automatic deployment is configured but blocked, not operational:** this account's organization policy denies GitHub OIDC provider creation, so `AWS_DEPLOY_ROLE_ARN` cannot currently be configured. The workflow reports that blocker instead of silently skipping or using permanent keys. Its future trust policy must restrict `aud=sts.amazonaws.com` and `sub=repo:mandziuk911/spry-lab:ref:refs/heads/main`. Updates currently use the local commands above. The shared origin token is retrieved from Secrets Manager for both deployments; neither AWS keys nor database/origin passwords are stored in GitHub secrets. AWS Builder ID/provider MFA remains unconfirmed and must be enabled through AWS Settings or the sign-in provider. Do not infer its status from the managed account's IAM root summary.

RDS deletion protection and resource retention are intentional. There is no automatic destructive teardown target. Before removing cloud resources, review snapshots/retained storage and confirm data loss; stopping only Fargate does not stop the other costs.

## Remaining lab deliverables

The original list/create milestone passed 41 backend tests, 15 frontend tests, Ruff/ESLint/Prettier, production frontend build, three-service Docker startup, API create/list/validation, persistence after restart, and database-outage 503/recovery. The deletion/retro-design extension passed 48 backend and 23 frontend tests, Ruff/ESLint/Prettier and a production build on pinned Node 24.0.0 (including frontend tests in a non-UTC timezone). Real Chrome checks passed creation/reload, cancellation, confirmed deletion, duplicate protection, preserved draft input, simulated 503 retention and another client's 404. Deleted rows stayed absent after all three services restarted; existing meetings were retained. Mobile layouts at 390px and 320px had no horizontal overflow. The live-status amendment passed all 38 frontend tests on pinned Node 24.0.0, including a non-UTC timezone, exact boundary/offset/DST checks, and timer cleanup. Actual Chrome verified automatic status/color transitions, one-hour hiding without extra API requests, database retention and hidden state after reload, preserved drafts, and 390px/320px layouts. No backend, schema migrations or dependency versions changed for this amendment. Lab 1 reference images have not been supplied, so reference-style compliance is unverified.

Remaining requirements include reference-image styling, a deliberately failing then fixed lint run, MFA verification, owned HTTPS domains/end-to-end ALB TLS and main-branch GitHub OIDC deployment. AWS configuration is implemented but public deployment/acceptance is pending; do not treat template existence as deployment proof.

Submit the public fork link, frontend screenshot and both deployed HTTPS URLs. The original assignment allowed a private cloned-and-pushed copy too, provided the lecturer had access.
