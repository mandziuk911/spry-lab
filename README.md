# Spry

Official public course fork: [mandziuk911/spry-lab](https://github.com/mandziuk911/spry-lab), forked from [dobosevych/OneTwoThree](https://github.com/dobosevych/OneTwoThree), preserving its history. The earlier private `mandziuk911/spry` repository remains a backup. The reviewed structure and API contract live in [PROJECT.md](PROJECT.md).

**Lab 4 authentication is being implemented and is not yet publicly validated/deployed.** The contracts below describe the new target; the previous deployment/test results at the end are historical, not proof of Cognito acceptance.

## Local startup

Install and start Docker Desktop. **Cognito sign-in is mandatory locally as well as on AWS.** Once the reviewed auth stack exists, fetch its public settings from the repository root:

```bash
aws login --profile spry --region eu-north-1
make auth-config                    # writes public settings to ignored .env
# Alternatively fill the three COGNITO_* fields from .env.example with auth outputs.
docker compose up --build
```

No AWS keys, Google secret or production database password are needed by the app. Missing/partial Cognito configuration fails closed; there is no anonymous demo fallback. No host Python/Node or manual database migration is required. After configuration and the first build, `docker compose up` starts the same three services. Published ports bind only to localhost.

- Frontend: http://localhost:5173
- Start sign-in: http://localhost:5173/login/
- Callback: http://localhost:5173/auth/callback/ (must match the Cognito allowlist exactly)
- Backend: http://localhost:8000
- API docs: http://localhost:8000/api/docs
- Readiness: http://localhost:8000/api/health

Guests see a retro welcome and Sign in, without meeting data or requests. Sign in with email/password or Google through Cognito; the header shows your email. Then create a meeting with title, start, end and attendee count. Reload the page: it remains saved. Status follows the live browser clock: **Scheduled** (gray) before the start, **In progress** (green) between start and end, and **Finished** (gray) after the end. One hour after its end, a meeting hides from the default list and sidebar counts, but is **not deleted** and remains available through the API. Status updates every second and when returning to the tab; no separate calendar integration or background database job is involved. Use a meeting's Delete control and confirm to permanently remove it; cancellation makes no request. An empty database has no sample meetings.

The page uses a retro 2000s desktop/web style: glossy title bars, beveled controls and colorful appointment panels. This is a user-requested redesign, not a claim of matching the missing lab reference screenshots.

## Structure

- `back/`: FastAPI HTTP routers, Pydantic contracts, service logic, SQLAlchemy model, Alembic migrations and tests.
- `front/`: one React/Vite page, Tailwind and committed shadcn/ui primitives.
- `compose.yaml`: PostgreSQL, backend and frontend; health-based dependency ordering and persistent `pgdata` volume.
- `.github/workflows/`: automated quality checks.
- `infra/` and `Makefile`: reviewed Free-plan ECS/ALB/RDS and private S3/CloudFront configuration plus shared deploy commands. A separate reviewed Cognito auth stack adds sign-in; obsolete Lambda/Aurora/domain recipes stay removed. Cloud usage consumes credits.

The first three migration files are preserved from the course repository. A forward migration adapts their schema to the minimal slice. Migrations execute at container startup before the API serves requests, never during image build. Review destructive migrations before using valuable data; see the new migration's downgrade warning.

## Contract

`GET /api/meetings` returns an ordered JSON array. `POST /api/meetings` accepts exactly `title`, `starts_at`, `ends_at`, `attendee_count` and returns those fields plus a UUID `id` with HTTP 201. Dates require a timezone and responses use UTC. End must follow start; title must contain 1–200 trimmed characters; count must be a nonnegative integer. Invalid requests return 422. Database failures return 503.

`DELETE /api/meetings/{meeting_id}` permanently deletes one meeting by UUID and returns HTTP 204 with no body. A missing/already-deleted UUID returns 404 (`Meeting not found`); malformed UUID returns 422; database failures return 503. The UI confirms before deleting, prevents duplicate requests and keeps the meeting visible if deletion fails. An already-deleted meeting is removed from a stale local list with an explicit message.

**Authenticated shared workspace, not author protection:** every signed-in user may list, create and delete any meeting. Meeting API calls require `Authorization: Bearer <access token>`; ID tokens, missing/invalid/expired tokens and wrong pools/clients receive 401. JWT verification-service failures fail closed with a generic 503. `/api/health`, CORS preflight, `/api/docs` and OpenAPI documentation are public; public documentation does not expose meeting data or bypass API authentication. Participant management, editing, ownership and analytics remain out of scope.

The OIDC library handles state/PKCE and access-token renewal using a valid refresh token. Session data stays in sessionStorage, not persistent localStorage; it is not immune to XSS. Terminal expiry hides meeting data and offers sign-in. POST/DELETE are never replayed automatically. A draft survives reauthentication only for the same issuer/sub in the same tab, not another account with the same email. Successful creation and explicit Sign out clear the saved draft. Sign out uses Cognito's `/logout`; a previously issued access token may remain valid until its short expiry.

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

The `spry` development credentials, Vite server, local CORS origin and published API port are for your laptop only. PostgreSQL is not published to the host. VITE settings are public browser configuration, never secrets. `.env` is ignored by Git: Cognito public settings are required, while database overrides are optional. Use AWS CLI profiles locally and OIDC for CI, not committed access keys.

## AWS deployment (Free-plan lab/demo)

Prerequisites: Docker, Python 3, current AWS CLI, a clean committed checkout and temporary credentials:

```bash
aws login --profile spry --region eu-north-1
make aws-check
# Google OAuth setup/publication and private JSON input must be prepared first.
make deploy-auth
make auth-config
make deploy-backend
make deploy-frontend
make aws-outputs
```

The tooling refuses another account, root/IAM-user credentials, non-ACTIVE/non-Free plans or fewer than $20 remaining credits. It does not upgrade the account, purchase domains or load AWS keys from `.env`. A temporary Free-plan credit balance is not permanent free hosting; ALB, public IPv4, Fargate, RDS, secrets, storage and logs continuously consume credits.

CloudFront's default HTTPS hostname serves frontend and `/api` on the same origin. Its ALB origin uses HTTP: this is not end-to-end TLS and does not fulfill the lab's custom-domain requirement. S3 and PostgreSQL are private; ALB accepts CloudFront-origin traffic plus a secret header, and tasks accept only ALB traffic. Local database data is never uploaded. This authenticated workspace is still shared among all signed-in users, not a sensitive multi-tenant product.

The backend uses Linux ARM64 SHA-tagged immutable ECR images and Secrets Manager DATABASE_URL injection, with PostgreSQL TLS. Production RDS pins available PostgreSQL 16.15; local Docker remains 16.8. Deployment first pauses the demo service, runs one Alembic task, checks its exit code, then enables the service and waits for stability. Failure stops deployment without deleting protected database data; recover explicitly after inspecting errors. This demo workflow is not zero-downtime deployment. No automatic irreversible migration downgrade is attempted.

Frontend builds on pinned Node 24.0.0 with `VITE_API_URL=/` and public Cognito configuration read from auth-stack outputs. `/login/` and `/auth/callback/` have narrow static-route rewrites; API errors are never rewritten to HTML. Hashed assets upload before `index.html`; older assets remain for rollback. CloudFront invalidations are awaited. Private origin-token/deployment state is stored outside Git in `~/.local/state/spry-aws/`; never publish the origin-token file.

Quality CI runs without AWS credentials. A separate main-only workflow waits for all quality checks, checks out their exact SHA, obtains OIDC temporary credentials via `aws-actions/configure-aws-credentials@v4`, and invokes the same Makefile targets. It does not cancel running migrations. **Automatic deployment is configured but blocked, not operational:** this account's organization policy denies GitHub OIDC provider creation, so `AWS_DEPLOY_ROLE_ARN` cannot currently be configured. The workflow reports that blocker instead of silently skipping or using permanent keys. Its future trust policy must restrict `aud=sts.amazonaws.com` and `sub=repo:mandziuk911/spry-lab:ref:refs/heads/main`. Updates currently use the local commands above. The shared origin token is retrieved from Secrets Manager for both deployments; neither AWS keys nor database/origin passwords are stored in GitHub secrets. AWS Builder ID/provider MFA remains unconfirmed and must be enabled through AWS Settings or the sign-in provider. Do not infer its status from the managed account's IAM root summary.

RDS automated backup retention is one day: the Free account rejected the initially proposed seven-day retention. RDS deletion protection and resource retention are intentional. There is no automatic destructive teardown target. Before removing cloud resources, review snapshots/retained storage and confirm data loss; stopping only Fargate does not stop the other costs.

## Google OAuth prerequisite (Lab 4)

In your own Google Cloud project, configure Google Auth Platform with an **External** audience, only `openid`, `email`, `profile`, and publishing status **In production**. Do not enable billing or unrelated APIs. Create a **Web application** OAuth client with:

- JavaScript origin: `https://spry-lab-673478369996.auth.eu-north-1.amazoncognito.com`
- Redirect URI: `https://spry-lab-673478369996.auth.eu-north-1.amazoncognito.com/oauth2/idpresponse`

Save its downloaded JSON privately as `~/.local/state/spry-aws/google-oauth.json` and `chmod 600` it. The tooling requires the exact redirect in `web.redirect_uris`. Never commit, print or upload this file. The Google secret is passed only to the auth template's NoEcho parameter; it is never a VITE value. The five-resource `infra/auth.yaml` enables verified-email self-signup, a public authorization-code client, Google federation and managed login v2. Pool retention/deletion protection deliberately prevents automatic account deletion on rollback.

Deploy the auth stack before the protected backend/frontend. Existing frontend hostname is retained. Confirm both production and localhost callback/logout URLs, including trailing slashes; `/login/` must start in Spry so the OIDC library creates state/PKCE. A password account and a Google account with the same email can have different Cognito subs; no automatic linking is performed.

Lab 4 submission: `/login/` URL, two actual site screenshots with email visible (password and Google), and a commit link containing auth infrastructure/frontend changes. Google must work for a non-test user and self-signup must stay enabled. API JWT protection is the selected stretch goal. Reading the migration does not require changing our ECS/RDS deployment to Lambda/Aurora.

## Historical Lab 1/2 validation and remaining deliverables

The original list/create milestone passed 41 backend tests, 15 frontend tests, Ruff/ESLint/Prettier, production frontend build, three-service Docker startup, API create/list/validation, persistence after restart, and database-outage 503/recovery. The deletion/retro-design extension passed 48 backend and 23 frontend tests, Ruff/ESLint/Prettier and a production build on pinned Node 24.0.0 (including frontend tests in a non-UTC timezone). Real Chrome checks passed creation/reload, cancellation, confirmed deletion, duplicate protection, preserved draft input, simulated 503 retention and another client's 404. Deleted rows stayed absent after all three services restarted; existing meetings were retained. Mobile layouts at 390px and 320px had no horizontal overflow. The live-status amendment passed all 38 frontend tests on pinned Node 24.0.0, including a non-UTC timezone, exact boundary/offset/DST checks, and timer cleanup. Actual Chrome verified automatic status/color transitions, one-hour hiding without extra API requests, database retention and hidden state after reload, preserved drafts, and 390px/320px layouts. No backend, schema migrations or dependency versions changed for this amendment. Lab 1 reference images have not been supplied, so reference-style compliance is unverified.

The [intentional Ruff F401 failure](https://github.com/mandziuk911/spry-lab/actions/runs/36908644988) and [subsequent green fix](https://github.com/mandziuk911/spry-lab/actions/runs/36908774252) were demonstrated on isolated ci/lint-demonstration; its final code is identical to main. [Main quality CI passed](https://github.com/mandziuk911/spry-lab/actions/runs/36908070103). Remaining requirements include reference-image styling, MFA verification, owned HTTPS domains/end-to-end ALB TLS and operational main-branch GitHub OIDC deployment. AWS deployment is live: frontend https://d7sqayh9iaw1u.cloudfront.net and backend https://d7sqayh9iaw1u.cloudfront.net/api/meetings (docs at /api/docs). Both application artifacts were deployed from dde9c363153bfe11defecfa76aaccf41f1ae51c1. Real Chrome/public API checks passed same-origin assets/GET/POST/DELETE, exact 201/204/404/422 JSON without stale caching/error rewriting, creation/reload/cancel/deletion, live status, 390px/320px layouts and no page errors. Direct S3 index access returned 403; ECS was 1/1 with completed rollout; RDS was available, private, encrypted and deletion-protected with one-day backups. Temporary test rows were removed. Account remained FREE ACTIVE and reported $120 credits after earned credit. Manual deployment works; the explicitly blocked OIDC workflow is not equivalent to successful CD. These results do not prove owned-domain, MFA or reference-style compliance. LMS submission is not complete.

Submit the public fork link, frontend screenshot and both deployed HTTPS URLs. The original assignment allowed a private cloned-and-pushed copy too, provided the lecturer had access.
