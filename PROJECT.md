# Spry — reviewed structure before implementation

**Status: minimal-slice implementation authorized by the human after selecting “Follow the lab scope” and requesting continuation.** This document specifies the target, not a claim that the inherited application already complies. Validate the implementation against the acceptance gate below.

## 1. Repository decision

Use one monorepo for the API, frontend, database migrations, local orchestration and CI/deployment configuration. Atomic commits keep API and client contracts together. More importantly, the repository is the agent's context window: it can inspect the endpoint, model, migration and consuming component together. Separate repositories buy release independence but cost shared context. For this small team and first product slice, context is worth more.

Source: https://github.com/dobosevych/OneTwoThree. Official public fork: https://github.com/mandziuk911/spry-lab (GitHub parent dobosevych/OneTwoThree). The earlier private https://github.com/mandziuk911/spry remains a backup. Preserve source Git history, keep the source as `upstream`, and never push to the course repository.

## 2. Approved direction and inherited-code boundary

The human selected the minimal lab scope rather than retaining the full course application. Keep the existing names `back/`, `front/` and `compose.yaml`: they are equivalent to the example's backend/frontend/docker-compose names. Do not create parallel applications or a second Compose file.

After approval, adapt the inherited application deliberately:

- Keep FastAPI, SQLAlchemy, Alembic, React, Vite, Tailwind and needed shadcn/ui components.
- Retain Python `pyproject.toml`/`uv.lock` and frontend `package.json`/`package-lock.json`; make dependency installation reproducible.
- The active slice has list/create/delete meetings, one page, and a supporting health endpoint. The human requested deletion and a retro 2000s redesign as a follow-up amendment. Remove inherited authentication/ownership coupling, participant management, editing and extra application routes from this slice. Replace tests that assert those superseded contracts with tests of the contract below. Deletion is deliberately unauthenticated, not restricted to an author; do not simulate ownership with browser storage.
- Keep UUID meeting identifiers from the source: the assignment specifies an id but does not require integers. Store `attendee_count` as an integer rather than deriving it from participant records.
- Preserve existing migration files. Add a forward migration, never rewrite applied migration history. Preserve existing meetings and identifiers; backfill counts from existing participant associations before removing obsolete relationships/tables. Remove obsolete non-null ownership/location requirements. Define a real downgrade or explicitly document any irreversible data loss. Review this migration separately before execution on any database with valuable data.
- Local frontend serving becomes Vite on port 5173. Remove the local Nginx configuration and proxy dependency; no reverse proxy is needed for this slice. Production frontend deployment will use S3/CloudFront, not a server container.
- Keep inherited CI/Makefile/infra files as source material, not as evidence that deployment works. Update their references only when needed, and review their AWS behavior before running any provisioning or deployment target. Do not add Cognito, Lambda or unrelated infrastructure to the required ECS/S3 deployment.
- Root standalone `main.py` and `pyproject.toml`, Lambda-specific files and seed logic are not part of the slice. Remove them after confirming no retained tooling needs them. No seeding is needed.

No Redis, Celery, cache, extra database, Kubernetes, authentication or invented analytics. Do not invent week-over-week numbers. The human now requests a 2000–2010 retro desktop/web design instead of minimalism: glossy gradients, beveled controls, strong panel borders, readable system fonts and responsive layouts. Reference-image compliance remains unverified; this customized design is not claimed to match missing Lab 1 screenshots.

## 3. Version policy

Pin exact direct dependency versions and commit transitive lockfiles. No `latest`, caret, tilde or lower-bound-only dependency declarations. Use frozen Python lock installation and `npm ci`. Keep existing compatible locked package versions where possible; do not downgrade solely to match an example. The inventory below is taken from the inherited lockfiles, not from a successful install. Validate package availability and compatibility before generation; if validation fails, propose and record replacement pins before code changes.

Chosen container/runtime versions:

| Component | Pin |
| --- | --- |
| Python backend base | python:3.12.10-slim-bookworm |
| PostgreSQL | postgres:16.8-bookworm |
| Frontend Node base | node:24.0.0-bookworm-slim |

Use uv image ghcr.io/astral-sh/uv:0.6.17 to supply the installer. Validate runtime and lockfile compatibility before generation; amend pins rather than silently changing them. shadcn/ui consists of committed component source, not a separate runtime service; retain only the primitives needed by the list/form. Existing dependency version ranges are not acceptable final pins.

Required backend direct pins from uv.lock: FastAPI 0.141.1, Uvicorn 0.53.0, SQLAlchemy 2.0.54, Alembic 1.20.0, Psycopg 3.3.6, Pydantic 2.13.5, pydantic-settings 2.15.0. Retain appropriate standard/binary extras. Test/lint pins: pytest 9.1.1, httpx 0.28.1, Ruff 0.16.8. Remove Mangum and PyJWT from the slice when their Lambda/auth consumers are removed.

Required frontend direct pins from package-lock.json: React/react-dom 19.3.0, class-variance-authority 0.7.1, clsx 2.1.1, radix-ui 1.6.7, tailwind-merge 3.7.0, lucide-react 1.47.0. Keep only dependencies actually used by the minimal components; remove the inherited router, command menu, authentication, theme, toast and form/query abstractions if no longer used.

Frontend build/test/lint pins from package-lock.json: Vite 8.3.0, @vitejs/plugin-react 6.1.1, TypeScript 6.0.3, Tailwind/@tailwindcss/vite 4.3.3, @types/node 26.6.2, @types/react/@types/react-dom 19.3.0, @eslint/js 10.0.1, ESLint 10.11.0, eslint-plugin-react-hooks 7.1.1, eslint-plugin-react-refresh 0.5.7, globals 17.12.0, typescript-eslint 8.70.0, Prettier 3.9.8, prettier-plugin-tailwindcss 0.8.1, Vitest 4.1.11, jsdom 29.1.1, @testing-library/jest-dom 7.0.1, @testing-library/react 16.3.3, @testing-library/user-event 14.6.7. Retain tw-animate-css 1.4.0 only if UI styling imports it. Review the Node type/runtime major mismatch during compatibility validation; do not assume lockfile presence proves compatibility.

## 4. Folder and file responsibilities

Every generated or retained active folder must have a purpose below. Do not create empty placeholders.

| Path | Purpose |
| --- | --- |
| PROJECT.md | Human-reviewed structure and contracts. |
| README.md | Prerequisites, one-command startup, URLs, troubleshooting and development/production differences. |
| .gitignore, .env.example | Exclude secrets/generated artifacts; document optional development overrides without real credentials. |
| compose.yaml | Three-service local orchestration, development defaults, ports, health checks and persistent database volume. |
| back/ | API, migrations, dependency manifest/lock and Dockerfile. |
| back/app/ | Python package containing app assembly, environment configuration, ORM engine/session lifecycle, table models and validation schemas. Existing main.py/config.py/db.py/models.py/schemas.py separate these concerns. |
| back/app/routers/ | HTTP layer: meetings routes and health, validation/status codes, not schema creation or business SQL. |
| back/app/services/ | Meeting listing/creation/deletion, transaction boundaries and storage-error handling. |
| back/alembic/ | Migration environment and template; obtain database URL from environment. |
| back/alembic/versions/ | Preserved schema history plus reviewed forward migration for this slice. |
| back/tests/ | API validation, persistence and health/error-contract checks. |
| front/ | React application, Dockerfile, exact dependency manifest/lock and Vite/TypeScript/lint configuration. |
| front/src/ | App mounting, single meeting page, typed contracts and Tailwind styles in index.css. |
| front/src/components/ | Meeting list and creation form; loading, empty, failure and submission states. |
| front/src/components/ui/ | Required committed shadcn/ui primitives, such as buttons, inputs, labels and cards. |
| front/src/lib/ | Typed API client and UI utilities; never database access. |
| front/src/test/ | Frontend test setup and focused component/client tests. |
| .github/workflows/ | CI checks; reviewed deployment automation in the later AWS stage. |
| infra/ | Reviewed AWS CloudFormation templates, temporary-credential deployment script, offline safety tests and pinned tooling requirements/lock. No provisioning during local startup. |
| Makefile | Local quality commands and later shared deploy-frontend/deploy-backend contracts. CI must invoke the same deploy recipes as developers. |

Dockerfiles answer how an individual service image is built/run. Compose answers how the local services connect and wait; it is not the production ECS architecture.

## 5. Local service contract

Docker Desktop with Compose v2 is the only required local runtime. A clean checkout starts with `docker compose up`; use `docker compose up --build` to explicitly rebuild after changes. No manual .env copy, host Python/Node install, manual database setup or manual migration.

| Service | Container / host port | Dependencies and readiness |
| --- | --- | --- |
| db | PostgreSQL 5432; no host port published | No upstream dependency. pg_isready checks configured database/user; interval 5s, timeout 5s, start period 10s, retries 12. |
| backend | 0.0.0.0:8000 / localhost:8000 | depends_on db with condition service_healthy. At container startup run alembic upgrade head, then Uvicorn; migration failure prevents serving. Python standard-library HTTP health check calls /api/health; interval 5s, timeout 5s, start period 20s, retries 12. |
| frontend | Vite 0.0.0.0:5173 / localhost:5173 | depends_on backend with condition service_healthy; Vite strict port. No Nginx/proxy. |

Compose provides development-only defaults: database/user/password `spry`/`spry`/`spry`, backend DATABASE_URL using the `db` hostname and Psycopg driver, CORS_ORIGINS allowing exactly http://localhost:5173, and frontend VITE_API_URL equal to http://localhost:8000. Keep the source's VITE_API_URL name; do not invent a second configuration key. Browser requests use localhost, never the Compose hostname `backend`. VITE variables are public configuration, never secrets.

Optional ignored environment overrides must not be required for startup. No real keys or production passwords are committed. Published API port, development credentials, Vite server and local origins are development-only.

Database volume `pgdata` mounts at /var/lib/postgresql/data. Restart and compose down preserve data; down -v intentionally destroys it. Migrations run at startup, not image build. Never use Base.metadata.create_all() for schema management. Copy source into application images initially; rebuild after changes instead of adding bind-mount complexity.

Readiness is not permanent availability. Enable SQLAlchemy pool_pre_ping and bounded database connection/query timeouts. If the database later disappears, roll back transactions, return a generic HTTP 503 for database-backed requests and log diagnostics without exposing SQL or credentials. Do not retry POST automatically: the commit outcome may be uncertain. New requests recover after connectivity returns.

## 6. Concrete meeting/API contract

Public meeting fields, and no others:

| Field | Type/rules |
| --- | --- |
| id | Database-generated UUID, serialized as a canonical UUID string; not client-selectable. |
| title | String trimmed of surrounding whitespace, length 1–200 after trimming. |
| starts_at | Timezone-aware ISO 8601 string, offset or Z mandatory. |
| ends_at | Timezone-aware ISO 8601 string, strictly after starts_at. |
| attendee_count | Strict integer >= 0; no booleans or numeric strings. |

PostgreSQL stores timezone-aware timestamps; responses serialize UTC with Z. Database constraints enforce non-null fields, valid duration and nonnegative count. Title validation remains authoritative in the API, with matching storage length. No uniqueness restriction on title.

### GET /api/meetings

HTTP 200, application/json array. Each element contains exactly the five fields above. Empty database returns an empty array. Order starts_at ascending then id ascending. No envelope, pagination or authentication.

### POST /api/meetings

JSON object with exactly title, starts_at, ends_at and attendee_count; all required. Reject unknown fields including id. Validate before writing, commit one meeting, return HTTP 201 with the complete five-field object. Validation failures return HTTP 422 with FastAPI's standard validation detail array. Database unavailability returns HTTP 503 with a generic detail message. No ownership or participant IDs.

### DELETE /api/meetings/{meeting_id}

UUID path parameter. Delete one matching row transactionally and return HTTP 204 with an empty body. Unknown/already-deleted UUID returns HTTP 404 with detail `Meeting not found`; malformed UUID returns standard HTTP 422. Database unavailability returns generic HTTP 503 with detail `Database unavailable`, with rollback and bounded waits as for other storage operations. No automatic retries, no authentication or author protection. No schema migration is required. This is an explicitly authorized extension beyond the original list/create lab slice; any client can delete any meeting, so authenticated ownership must be reviewed before sensitive public use.

### GET /api/health

Supporting readiness endpoint, not another product feature. Lightweight database query; HTTP 200 with status equal to ok if reachable, otherwise HTTP 503 with status equal to unavailable. Keep this inherited health response shape. Never expose connection information.

HTTP routers validate/adapt, services own ORM operations/transactions, schemas define public contracts and models define storage. Browser never connects directly to PostgreSQL.

## 7. Frontend contract

One page shows a heading, list and creation form. Each meeting shows title, start, end and attendee count. Show a clear timezone label and render times in the browser's local timezone.

Form fields: title, local start/end datetime inputs and attendee count. Convert valid local datetime values to UTC ISO 8601 before sending; validate duration/count client-side while retaining backend authority.

Fetch on initial load. Distinguish loading, empty and error states. Disable duplicate submits. On HTTP 201 reset the form and fetch the sorted list again. If creation succeeds but refresh fails, say so instead of calling creation a failure. Preserve input on failed creation. No automatic POST retries and no fake data masking errors.

Each meeting has an accessible Delete control. Ask for confirmation showing the title and stating deletion is permanent; cancel sends no request. Disable duplicate deletion while pending. Successful 204 removes the meeting from the local list and announces success without relying on a refresh. A 404 means another client already removed it: remove the stale item and announce that distinction. Other failures keep the meeting visible and show a retryable error; do not silently treat 503/network failure as deletion success or automatically retry. Preserve form input when another meeting is deleted. Prevent stale list requests or competing creation refreshes from resurrecting a deleted row. A visible note states that this workspace has no accounts and anyone with API access can delete meetings.

### Live meeting status amendment

The human approved automatic statuses driven by the browser's current date/time, not a separate calendar screen or external-calendar integration. Derive status from the existing timezone-aware timestamps: `Scheduled` when now < starts_at; `In progress` when starts_at <= now < ends_at; `Finished` when now >= ends_at. Use readable gray text for Scheduled/Finished and green for In progress, with explicit text labels so color is not the only indication.

Hide a meeting from the default list at now >= ends_at + 3,600,000 milliseconds. This is presentation-only: retain the full fetched array, database row and unchanged API contract. Do not issue DELETE, persist a hidden flag, add a migration, scheduler or dependencies. Refresh the clock every second while mounted and immediately on window focus/document visibility changes to recover after a sleeping/throttled tab. Compare absolute timestamps, not local-clock strings, including across timezone/day/DST boundaries; local rendering stays unchanged.

Sidebar counts reflect visible meetings only. Distinguish a truly empty database from a list containing only hidden finished meetings; explain that finished meetings leave the list after one hour but remain saved. Clock updates must preserve creation drafts and deletion/request race protection. Existing confirmed manual deletion remains permanent and separate from automatic hiding.

Retro styling must retain form validation and loading/empty/error states, keyboard-visible focus, readable contrast, semantic headings/labels and responsive layout on narrow screens. Decorative window controls are not fake interactive actions. No fake stats, external fonts/assets or added dependencies are needed.

## 8. Review gate and local acceptance

The minimal-slice specification was committed before code changes, and the human authorized continuation. Validate the dependency pins during implementation and review the generated diff and forward migration before executing against valuable data. Any contract or version change requires an explicit specification amendment.

Then generate only the approved slice and review the diff. Verify:

- Clean checkout starts with docker compose up --build without preparation.
- Database health precedes migrations; migrations precede backend serving; backend health precedes frontend startup.
- Fresh database lists no meetings; creating a meeting returns 201 and displays it.
- Reload and Compose restart preserve meetings.
- Invalid titles, naive timestamps, duration/count violations and unknown fields return 422 without rows being added.
- Database outages produce 503 and visible client errors, not successful empty results.
- Deletion persists after reload/restart; cancel does nothing, unknown UUID yields 404, malformed UUID yields 422 and database outages yield 503.
- Frontend covers confirmed/cancelled deletion, pending duplicate protection, already-deleted handling, failure retention and preserved form input.
- Live status covers exact start/end/one-hour boundaries, timezone offsets and day rollover; hiding sends no API mutation and leaves records readable through GET, including after reload. Returning to a backgrounded tab refreshes status without a network request. Clock timers/listeners are cleaned up on unmount.
- Retro redesign renders at desktop and mobile widths without losing focus visibility or overflowing content.
- Only three Compose services exist; only the specified meeting routes and supporting health/docs routes remain active, without authentication.

## 9. Reviewed AWS deployment amendment

The human authorizes an autonomous lab/demo AWS deployment in account 673478369996, region eu-north-1, using its ACTIVE Free plan and promotional credits. Do not upgrade the account, activate advanced features, purchase a domain, ask the lecturer for access, or create long-lived AWS keys. Before each deployment verify the expected account, FREE/ACTIVE plan and at least USD 20 remaining credits; stop rather than change the plan if permissions or funding are insufficient. AWS service usage consumes credits continuously, even without visitors; Free plan is not permanent free hosting.

Deploy the frontend to a private encrypted S3 bucket with public access blocked, served only by CloudFront OAC. Use the default https://<distribution>.cloudfront.net hostname and same-origin /api and /api/* behaviors pointing to an HTTP ALB backed by one ECS Fargate ARM64 task (0.25 vCPU, 0.5 GiB). Viewer connections are HTTPS; CloudFront-to-ALB is HTTP, NOT end-to-end TLS. Protect ALB ingress with the CloudFront origin-facing managed prefix list and a secret origin header; task ingress only from the ALB security group. Disable API caching, preserve query strings and necessary headers, allow all HTTP methods including DELETE/OPTIONS, and never rewrite API 404/422/503 into HTML/200. No global SPA error rewrite is needed for this one-page app.

Use an immutable ECR image tagged with the full reviewed commit SHA, built from the retained pinned backend Dockerfile. Build both applications from a temporary git-archive snapshot, excluding uncommitted files/generated dependencies; serialize deployment commands with a private local file lock. Replace inherited Lambda/Aurora/Cognito and certificate/domain recipes with the required architecture. No NAT gateway or paid private endpoints: tasks use public subnets/public IPv4 for outbound image/log/secret access but no direct inbound access. Database uses private subnets, a PostgreSQL-only security group accessible solely from the task/migration group, Single-AZ db.t4g.micro, 20 GiB gp3, encryption, deletion protection and retained backups. The local Postgres 16.8 pin is unchanged; RDS no longer offers 16.8 here, so production explicitly pins supported PostgreSQL 16.15. No copying of local/private meeting data into the public workspace.

Use Secrets Manager for a generated strong database password and a derived DATABASE_URL secret with sslmode=require. ECS injects DATABASE_URL through secret references; no passwords in task environment plaintext, repository, GitHub secrets, stack outputs or logs. Preserve the application's existing DATABASE_URL contract and all dependency pins. Bootstrap a retained Secrets Manager generated 64-hex origin token with ECR; local and future OIDC jobs retrieve the same value, cache it privately (0600) outside Git, and pass it as a NoEcho parameter to both templates. Never commit/print it or store it in GitHub secrets.

Bootstrap ECR first, build/push the exact SHA image, then create networking/database/ALB/cluster/task definitions with service desired count zero. Subsequent demo deployments intentionally pause the service during migration; failures retain resources and serving remains disabled until explicit recovery. This is not a zero-downtime production release system. Run one controlled Fargate Alembic task, wait for completion and require exit code zero before enabling the service. Service startup runs Uvicorn only, not migrations in every replica; local Compose startup remains unchanged. ALB checks /api/health. Enable ECS circuit-breaker rollback and wait for service stability. Never automatically downgrade the irreversible 0004 migration. Keep database deletion protection and retention; destructive teardown is a separate explicit snapshot/data decision, not an automatic deploy-failure cleanup.

Offline infrastructure validation uses cfn-lint 1.44.0 and Ruff 0.16.8 with committed infra/requirements.lock; CI installs the lock on Python 3.12.10 and runs eleven stdlib safety tests without AWS credentials. Publish frontend with pinned Node 24.0.0 and npm ci, VITE_API_URL=/ for same-origin requests. Upload fingerprinted assets before index.html, retain old assets for rollback, invalidate CloudFront and wait for completion. Developers use make deploy-backend and make deploy-frontend; both run shared deployment tooling and safety guards. Existing quality CI continues on pushes and PRs. GitHub OIDC is explicitly denied by this account's organizational policy; do not substitute persistent keys or temporary session secrets in GitHub. For this approved Free-plan-only deployment, cloud updates currently run locally with temporary aws login credentials. A main-only OIDC workflow is configured to await successful quality checks, check out their exact SHA and invoke the same Makefile targets. It must fail visibly when AWS_DEPLOY_ROLE_ARN is absent; automatic deployment is blocked/not operational, not silently claimed complete. A future trust must restrict aud=sts.amazonaws.com and sub=repo:mandziuk911/spry-lab:ref:refs/heads/main. Do not upgrade the account to resolve this denial.

Security: the new managed-signup experience uses AccountFullAccessRole and has no user-created root. Verify MFA through AWS Settings/Builder ID or the upstream sign-in provider, not IAM's root-MFA summary. User MFA remains unconfirmed; only disposable public lab data is permitted and this security criterion must be reported pending. No application accounts/author-only deletion are added.

Acceptance: validate templates/scripts and local quality first; verify public HTTPS frontend/assets, JSON health/list/create/delete, exact 201/204/404/422 responses and uncached list updates through CloudFront, real browser form creation/reload/deletion and mobile layout. Confirm local data is untouched and account remains FREE. Record deployed URLs, image SHA and infrastructure state without secrets. Owned-domain HTTPS, end-to-end ALB TLS, GitHub automatic OIDC deployment, intentional lint-failure demonstration, reference-image styling and lecturer repository access remain separate incomplete submission items.
