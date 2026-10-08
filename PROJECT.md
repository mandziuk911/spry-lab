# Spry — reviewed structure before implementation

**Status: the human reviewed the Lab 4 specification in section 10 and explicitly authorized implementation, tests, commits/push and deployment on the existing Free plan.** Authentication is not implemented or validated merely because it is specified here. Keep the stated account/funding/secret guards, no paid upgrades or purchases, and validate actual dependency/runtime behavior and acceptance before claiming completion.

## 1. Repository decision

Use one monorepo for the API, frontend, database migrations, local orchestration and CI/deployment configuration. Atomic commits keep API and client contracts together. More importantly, the repository is the agent's context window: it can inspect the endpoint, model, migration and consuming component together. Separate repositories buy release independence but cost shared context. For this small team and first product slice, context is worth more.

Source: https://github.com/dobosevych/OneTwoThree. Official public fork: https://github.com/mandziuk911/spry-lab (GitHub parent dobosevych/OneTwoThree). The earlier private https://github.com/mandziuk911/spry remains a backup. Preserve source Git history, keep the source as `upstream`, and never push to the course repository.

## 2. Approved direction and inherited-code boundary

The human selected the minimal lab scope rather than retaining the full course application. Keep the existing names `back/`, `front/` and `compose.yaml`: they are equivalent to the example's backend/frontend/docker-compose names. Do not create parallel applications or a second Compose file.

After approval, adapt the inherited application deliberately:

- Keep FastAPI, SQLAlchemy, Alembic, React, Vite, Tailwind and needed shadcn/ui components.
- Retain Python `pyproject.toml`/`uv.lock` and frontend `package.json`/`package-lock.json`; make dependency installation reproducible.
- The implemented baseline has list/create/delete meetings, one workspace, and a supporting health endpoint. It removed inherited authentication/ownership coupling, participant management, editing and extra application routes. Baseline deletion is deliberately unauthenticated. The proposed Lab 4 amendment in section 10 adds Cognito authentication, not the old ownership system: every authenticated user may operate on shared meetings. Do not simulate ownership with browser storage.
- Keep UUID meeting identifiers from the source: the assignment specifies an id but does not require integers. Store `attendee_count` as an integer rather than deriving it from participant records.
- Preserve existing migration files. Add a forward migration, never rewrite applied migration history. Preserve existing meetings and identifiers; backfill counts from existing participant associations before removing obsolete relationships/tables. Remove obsolete non-null ownership/location requirements. Define a real downgrade or explicitly document any irreversible data loss. Review this migration separately before execution on any database with valuable data.
- Local frontend serving becomes Vite on port 5173. Remove the local Nginx configuration and proxy dependency; no reverse proxy is needed for this slice. Production frontend deployment will use S3/CloudFront, not a server container.
- Review CI/Makefile/infra behavior before running any provisioning or deployment target; files alone are not deployment proof. Cognito was excluded from the earlier ECS/S3 lab, but is now proposed specifically for Lab 4 in section 10. Lambda, Aurora and unrelated infrastructure remain outside the new implementation scope.
- Root standalone `main.py` and `pyproject.toml`, Lambda-specific files and seed logic are not part of the slice. Remove them after confirming no retained tooling needs them. No seeding is needed.

No Redis, Celery, application-data cache, extra database, Kubernetes or invented analytics. Authentication is limited to the proposed Cognito amendment in section 10; a bounded JWKS key cache is necessary for token verification, not a new cache service. Do not invent week-over-week numbers. The human now requests a 2000–2010 retro desktop/web design instead of minimalism: glossy gradients, beveled controls, strong panel borders, readable system fonts and responsive layouts. Reference-image compliance remains unverified; this customized design is not claimed to match missing Lab 1 screenshots.

## 3. Version policy

Pin exact direct dependency versions and commit transitive lockfiles. No `latest`, caret, tilde or lower-bound-only dependency declarations. Use frozen Python lock installation and `npm ci`. Keep existing compatible locked package versions where possible; do not downgrade solely to match an example. The inventory below is taken from the inherited lockfiles, not from a successful install. Validate package availability and compatibility before generation; if validation fails, propose and record replacement pins before code changes.

Chosen container/runtime versions:

| Component | Pin |
| --- | --- |
| Python backend base | python:3.12.10-slim-bookworm |
| PostgreSQL | postgres:16.8-bookworm |
| Frontend Node base | node:24.0.0-bookworm-slim |

Use uv image ghcr.io/astral-sh/uv:0.6.17 to supply the installer. Validate runtime and lockfile compatibility before generation; amend pins rather than silently changing them. shadcn/ui consists of committed component source, not a separate runtime service; retain only the primitives needed by the list/form. Existing dependency version ranges are not acceptable final pins.

Required backend direct pins from uv.lock: FastAPI 0.141.1, Uvicorn 0.53.0, SQLAlchemy 2.0.54, Alembic 1.20.0, Psycopg 3.3.6, Pydantic 2.13.5, pydantic-settings 2.15.0. Retain appropriate standard/binary extras. Test/lint pins: pytest 9.1.1, httpx 0.28.1, Ruff 0.16.8. The baseline removed Mangum and the unused authentication dependencies. Lab 4 proposes a maintained JWT library with cryptographic verification; its exact version and cryptographic dependency pins must be validated and reviewed before application changes. Mangum remains excluded.

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

Docker Desktop with Compose v2 is the required local application runtime. The unauthenticated baseline starts from a clean checkout without preparation; the human's Lab 4 decision supersedes that convenience: local authentication is mandatory, so a clean checkout will require public Cognito settings from the reviewed auth-stack outputs in an ignored local environment file. No AWS keys or Google client secret belong in application containers. Then use `docker compose up`, or `docker compose up --build` after changes. No host Python/Node install, manual database setup or manual migration; Compose must never provision AWS resources.

| Service | Container / host port | Dependencies and readiness |
| --- | --- | --- |
| db | PostgreSQL 5432; no host port published | No upstream dependency. pg_isready checks configured database/user; interval 5s, timeout 5s, start period 10s, retries 12. |
| backend | 0.0.0.0:8000 / localhost:8000 | depends_on db with condition service_healthy. At container startup run alembic upgrade head, then Uvicorn; migration failure prevents serving. Python standard-library HTTP health check calls /api/health; interval 5s, timeout 5s, start period 20s, retries 12. |
| frontend | Vite 0.0.0.0:5173 / localhost:5173 | depends_on backend with condition service_healthy; Vite strict port. No Nginx/proxy. |

Compose provides development-only defaults: database/user/password `spry`/`spry`/`spry`, backend DATABASE_URL using the `db` hostname and Psycopg driver, CORS_ORIGINS allowing exactly http://localhost:5173, and frontend VITE_API_URL equal to http://localhost:8000. Keep the source's VITE_API_URL name; do not invent a second configuration key. Browser requests use localhost, never the Compose hostname `backend`. VITE variables are public configuration, never secrets.

Database overrides remain optional. For Lab 4, complete public Cognito configuration is required for local startup; missing/partial configuration fails clearly rather than enabling an anonymous demo. No real keys or production passwords are committed. Published API port, development credentials, Vite server and local origins are development-only; propose binding published ports to loopback.

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

HTTP 200, application/json array. Each element contains exactly the five fields above. Empty database returns an empty array. Order starts_at ascending then id ascending. No envelope or pagination. The baseline is unauthenticated; section 10 proposes authentication for this route without changing its successful response.

### POST /api/meetings

JSON object with exactly title, starts_at, ends_at and attendee_count; all required. Reject unknown fields including id. Validate before writing, commit one meeting, return HTTP 201 with the complete five-field object. Validation failures return HTTP 422 with FastAPI's standard validation detail array. Database unavailability returns HTTP 503 with a generic detail message. No ownership or participant IDs.

### DELETE /api/meetings/{meeting_id}

UUID path parameter. Delete one matching row transactionally and return HTTP 204 with an empty body. Unknown/already-deleted UUID returns HTTP 404 with detail `Meeting not found`; malformed UUID returns standard HTTP 422. Database unavailability returns generic HTTP 503 with detail `Database unavailable`, with rollback and bounded waits as for other storage operations. No automatic retries or author protection. No schema migration is required. The baseline allows any client to delete any meeting; section 10 proposes restricting access to authenticated clients, while allowing every authenticated user to delete any shared meeting. Authentication does not establish ownership; sensitive multi-tenant use would require a separately reviewed authorization model.

### GET /api/health

Supporting readiness endpoint, not another product feature. Lightweight database query; HTTP 200 with status equal to ok if reachable, otherwise HTTP 503 with status equal to unavailable. Keep this inherited health response shape. Never expose connection information.

HTTP routers validate/adapt, services own ORM operations/transactions, schemas define public contracts and models define storage. Browser never connects directly to PostgreSQL.

## 7. Frontend contract

One page shows a heading, list and creation form. Each meeting shows title, start, end and attendee count. Show a clear timezone label and render times in the browser's local timezone.

Form fields: title, local start/end datetime inputs and attendee count. Convert valid local datetime values to UTC ISO 8601 before sending; validate duration/count client-side while retaining backend authority.

Fetch on initial load. Distinguish loading, empty and error states. Disable duplicate submits. On HTTP 201 reset the form and fetch the sorted list again. If creation succeeds but refresh fails, say so instead of calling creation a failure. Preserve input on failed creation. No automatic POST retries and no fake data masking errors.

Each meeting has an accessible Delete control. Ask for confirmation showing the title and stating deletion is permanent; cancel sends no request. Disable duplicate deletion while pending. Successful 204 removes the meeting from the local list and announces success without relying on a refresh. A 404 means another client already removed it: remove the stale item and announce that distinction. Other failures keep the meeting visible and show a retryable error; do not silently treat 503/network failure as deletion success or automatically retry. Preserve form input when another meeting is deleted. Prevent stale list requests or competing creation refreshes from resurrecting a deleted row. The baseline visibly identifies its unauthenticated mode. Under section 10, the production workspace instead identifies shared authenticated access: any signed-in user may delete any meeting. Do not keep an inaccurate “no accounts” note in the authenticated workspace.

### Live meeting status amendment

The human approved automatic statuses driven by the browser's current date/time, not a separate calendar screen or external-calendar integration. Derive status from the existing timezone-aware timestamps: `Scheduled` when now < starts_at; `In progress` when starts_at <= now < ends_at; `Finished` when now >= ends_at. Use readable gray text for Scheduled/Finished and green for In progress, with explicit text labels so color is not the only indication.

Hide a meeting from the default list at now >= ends_at + 3,600,000 milliseconds. This is presentation-only: retain the full fetched array, database row and unchanged API contract. Do not issue DELETE, persist a hidden flag, add a migration, scheduler or dependencies. Refresh the clock every second while mounted and immediately on window focus/document visibility changes to recover after a sleeping/throttled tab. Compare absolute timestamps, not local-clock strings, including across timezone/day/DST boundaries; local rendering stays unchanged.

Sidebar counts reflect visible meetings only. Distinguish a truly empty database from a list containing only hidden finished meetings; explain that finished meetings leave the list after one hour but remain saved. Clock updates must preserve creation drafts and deletion/request race protection. Existing confirmed manual deletion remains permanent and separate from automatic hiding.

Retro styling must retain form validation and loading/empty/error states, keyboard-visible focus, readable contrast, semantic headings/labels and responsive layout on narrow screens. Decorative window controls are not fake interactive actions. No fake stats, external fonts/assets or added dependencies are needed.

## 8. Review gate and local acceptance

The minimal-slice specification was committed before code changes, and the human authorized continuation. Validate the dependency pins during implementation and review the generated diff and forward migration before executing against valuable data. Any contract or version change requires an explicit specification amendment.

Then generate only the approved slice and review the diff. Verify:

- Baseline clean checkout starts without preparation. Lab 4 requires the documented public Cognito configuration first; with it, docker compose up --build starts the same three services, with no AWS provisioning or manual database work. Missing/partial auth configuration fails closed.
- Database health precedes migrations; migrations precede backend serving; backend health precedes frontend startup.
- Fresh database lists no meetings; creating a meeting returns 201 and displays it.
- Reload and Compose restart preserve meetings.
- Invalid titles, naive timestamps, duration/count violations and unknown fields return 422 without rows being added.
- Database outages produce 503 and visible client errors, not successful empty results.
- Deletion persists after reload/restart; cancel does nothing, unknown UUID yields 404, malformed UUID yields 422 and database outages yield 503.
- Frontend covers confirmed/cancelled deletion, pending duplicate protection, already-deleted handling, failure retention and preserved form input.
- Live status covers exact start/end/one-hour boundaries, timezone offsets and day rollover; hiding sends no API mutation and leaves records readable through GET, including after reload. Returning to a backgrounded tab refreshes status without a network request. Clock timers/listeners are cleaned up on unmount.
- Retro redesign renders at desktop and mobile widths without losing focus visibility or overflowing content.
- Only three Compose services exist. The baseline has no authentication; section 10 defines the proposed protected meeting routes, explicit public health/docs exceptions and frontend authentication routes.

## 9. Reviewed AWS deployment amendment

The human authorizes an autonomous lab/demo AWS deployment in account 673478369996, region eu-north-1, using its ACTIVE Free plan and promotional credits. Do not upgrade the account, activate advanced features, purchase a domain, ask the lecturer for access, or create long-lived AWS keys. Before each deployment verify the expected account, FREE/ACTIVE plan and at least USD 20 remaining credits; stop rather than change the plan if permissions or funding are insufficient. AWS service usage consumes credits continuously, even without visitors; Free plan is not permanent free hosting.

Deploy the frontend to a private encrypted S3 bucket with public access blocked, served only by CloudFront OAC. Use the default https://<distribution>.cloudfront.net hostname and same-origin /api and /api/* behaviors pointing to an HTTP ALB backed by one ECS Fargate ARM64 task (0.25 vCPU, 0.5 GiB). Viewer connections are HTTPS; CloudFront-to-ALB is HTTP, NOT end-to-end TLS. Protect ALB ingress with the CloudFront origin-facing managed prefix list and a secret origin header; task ingress only from the ALB security group. Disable API caching, preserve query strings and necessary headers, allow all HTTP methods including DELETE/OPTIONS, and never rewrite API 404/422/503 into HTML/200. Do not add a global SPA error rewrite. Lab 4 proposes narrowly scoped static-route handling for /login/ and /auth/callback/; API paths and error responses must remain untouched.

Use an immutable ECR image tagged with the full reviewed commit SHA, built from the retained pinned backend Dockerfile. Build both applications from a temporary git-archive snapshot, excluding uncommitted files/generated dependencies; serialize deployment commands with a private local file lock. Do not run inherited Lambda/Aurora/Cognito or certificate/domain recipes. Lab 4 may add a separately reviewed Cognito auth stack without replacing the existing ECS/RDS deployment. No NAT gateway or paid private endpoints: tasks use public subnets/public IPv4 for outbound image/log/secret access but no direct inbound access. Database uses private subnets, a PostgreSQL-only security group accessible solely from the task/migration group, Single-AZ db.t4g.micro, 20 GiB gp3, encryption, deletion protection and retained backups. Set automated backup retention to one day (minimum nonzero/API default): the actual Free-plan request rejected the originally proposed seven days. No paid upgrade to increase retention. The local Postgres 16.8 pin is unchanged; RDS no longer offers 16.8 here, so production explicitly pins supported PostgreSQL 16.15. No copying of local/private meeting data into the public workspace.

Use Secrets Manager for a generated strong database password and a derived DATABASE_URL secret with sslmode=require. ECS injects DATABASE_URL through secret references; no passwords in task environment plaintext, repository, GitHub secrets, stack outputs or logs. Preserve the application's existing DATABASE_URL contract and all dependency pins. Bootstrap a retained Secrets Manager generated 64-hex origin token with ECR; local and future OIDC jobs retrieve the same value, cache it privately (0600) outside Git, and pass it as a NoEcho parameter to both templates. Never commit/print it or store it in GitHub secrets.

Bootstrap ECR first, build/push the exact SHA image, then create networking/database/ALB/cluster/task definitions with service desired count zero. Subsequent demo deployments intentionally pause the service during migration; failures retain resources and serving remains disabled until explicit recovery. This is not a zero-downtime production release system. Run one controlled Fargate Alembic task, wait for completion and require exit code zero before enabling the service. Service startup runs Uvicorn only, not migrations in every replica; local Compose startup remains unchanged. ALB checks /api/health. Enable ECS circuit-breaker rollback and wait for service stability. Never automatically downgrade the irreversible 0004 migration. Keep database deletion protection and retention; destructive teardown is a separate explicit snapshot/data decision, not an automatic deploy-failure cleanup.

Offline infrastructure validation uses cfn-lint 1.44.0 and Ruff 0.16.8 with committed infra/requirements.lock; CI installs the lock on Python 3.12.10 and runs eleven stdlib safety tests without AWS credentials. Publish frontend with pinned Node 24.0.0 and npm ci, VITE_API_URL=/ for same-origin requests. Upload fingerprinted assets before index.html, retain old assets for rollback, invalidate CloudFront and wait for completion. Developers use make deploy-backend and make deploy-frontend; both run shared deployment tooling and safety guards. Existing quality CI continues on pushes and PRs. GitHub OIDC is explicitly denied by this account's organizational policy; do not substitute persistent keys or temporary session secrets in GitHub. For this approved Free-plan-only deployment, cloud updates currently run locally with temporary aws login credentials. A main-only OIDC workflow is configured to await successful quality checks, check out their exact SHA and invoke the same Makefile targets. It must fail visibly when AWS_DEPLOY_ROLE_ARN is absent; automatic deployment is blocked/not operational, not silently claimed complete. A future trust must restrict aud=sts.amazonaws.com and sub=repo:mandziuk911/spry-lab:ref:refs/heads/main. Do not upgrade the account to resolve this denial.

Security: the new managed-signup experience uses AccountFullAccessRole and has no user-created root. Verify MFA through AWS Settings/Builder ID or the upstream sign-in provider, not IAM's root-MFA summary. User MFA remains unconfirmed; only disposable lab data is permitted and this security criterion must be reported pending. Section 10 proposes Cognito application accounts; author-only deletion, application user tables and automatic account linking remain excluded.

Acceptance: validate templates/scripts and local quality first; verify public HTTPS frontend/assets, JSON health/list/create/delete, exact 201/204/404/422 responses and uncached list updates through CloudFront, real browser form creation/reload/deletion and mobile layout. Confirm local data is untouched and account remains FREE. Record deployed URLs, image SHA and infrastructure state without secrets. Owned-domain HTTPS, end-to-end ALB TLS, GitHub automatic OIDC deployment, reference-image styling and lecturer repository access require their own evidence; this authentication amendment does not resolve them. The intentional lint-failure demonstration has already been completed and must not be repeated as if missing.

## 10. Lab 4 — Cognito sign-in and protected shared meetings (reviewed)

### Source, approval and scope

Assignment: https://learn.ucu.edu.ua/mod/assign/view.php?id=152412, “Lab 4. From always-on to serverless, then a sign-in page”. Deadline displayed by LMS: 8 October 2026, 23:55. The assignment and attached architecture-migration.md were read through the human's authorized Safari session.

The human selected the mandatory Cognito sign-in implementation plus the optional API-protection stretch goal, shared meetings for all authenticated users, and a retro guest welcome with Sign in. They selected automatic token renewal and draft recovery for the same Cognito user, with draft clearing on explicit sign-out. **After reviewing the draft and metadata-checked dependency pins, the human selected “Реалізуй і розгорни”. Execution now includes application changes, agreed dependency/lockfile updates, testing, commits/push, Google OAuth setup/publication, Cognito IaC and app deployment.** Retain Free-plan-only restrictions and stop on permission, funding, billing-upgrade or personal-authentication blockers. This does not authorize an LMS submission.

The migration described in the reading is discussion material, not an instruction to migrate this application's backend. Retain ECS Fargate, ALB, private RDS, same-origin CloudFront API, existing meeting services and all migration files. No Lambda, Aurora, NAT, API Gateway, extra database, domain purchase, paid-plan upgrade or advanced-feature activation. Keep the existing retro styling and live-status behavior. No ownership field, application users table, author-only deletion, roles or automatic identity linking.

### Account and cost preflight

Read-only checks on 8 October 2026 confirmed account 673478369996, FREE/ACTIVE, USD 109.13 remaining credits and plan expiration 1 April 2027. No Cognito pools were listed in eu-north-1. Region-aware IAM simulation allowed CreateUserPool, CreateUserPoolClient, CreateIdentityProvider, CreateUserPoolDomain and CreateManagedLoginBranding, with no missing context and AllowedByOrganizations=true. **Simulation and read access are not proof that actual creation will succeed.** Recheck account, plan, funds and actual service restrictions before authorized provisioning; stop on refusal rather than changing plan or credentials strategy.

Official Cognito pricing lists a combined 10,000 monthly-active-user allowance for Essentials direct/password and social-provider users. Do not treat that as proof of all account-specific eligibility or promise unlimited free use. Existing ECS/ALB/RDS continue consuming credits. Preserve the USD 20 deployment guard, temporary aws login credentials, no long-lived keys, and the unresolved GitHub OIDC/SCP limitation. Google federation in Cognito is not creation of a GitHub IAM OIDC provider and does not fix automatic CD.

### Cognito and Google infrastructure

Propose infra/auth.yaml with exactly five Cognito resources, deployed only after separate approval:

1. UserPool: ESSENTIALS, email usernames, verified email, self-signup enabled and a documented password policy. Tag with the project's existing tagging convention.
2. UserPoolClient: public SPA client, GenerateSecret=false, authorization-code flow, openid/email/profile scopes, COGNITO and Google providers. Depend explicitly on the Google provider. Configure exact callback/logout allowlists; propose 15-minute ID/access tokens and a one-day refresh-token lifetime, subject to review and service validation.
3. UserPoolIdentityProvider: Google client ID and a NoEcho client-secret parameter; authorize only openid email profile and map at least email and email_verified.
4. UserPoolDomain: a unique prefix domain with ManagedLoginVersion=2; propose eu-north-1 to match the existing backend, not a move of any current stack.
5. ManagedLoginBranding: UseCognitoProvidedValues=true. Spry's welcome/workspace stay retro; the managed Cognito page uses Cognito-provided branding.

Outputs expose only pool ID, issuer, public app-client ID and managed-login/logout domain. Never output the Google secret or any tokens. Store the Google secret only in an ignored private local input and Cognito configuration; pass it through NoEcho without printing it, embedding it in frontend builds, template metadata/outputs or command logs. No additional Secrets Manager secret is required solely for this lab's Google input.

Google OAuth setup uses an External consent audience, minimal scopes and publishing status In production, so the lecturer is not restricted to a test-user list. Authorized Google redirect points to https://<prefix>.auth.eu-north-1.amazoncognito.com/oauth2/idpresponse, not directly to Spry. Its JavaScript origin is that Cognito domain. Do not enable Google billing or unrelated APIs. Google project/client setup and publication remain prerequisites, not completed work.

Use the current CloudFront hostname, verified from deployed outputs before execution. Proposed callback URLs are https://d7sqayh9iaw1u.cloudfront.net/auth/callback/ and http://localhost:5173/auth/callback/. Proposed logout URLs are https://d7sqayh9iaw1u.cloudfront.net/ and http://localhost:5173/. Preserve trailing slashes exactly. No wildcard callbacks, unvalidated return URLs or open redirects.

Password and Google sign-in can create different Cognito users/sub identifiers even when the email matches. Do not merge automatically on email. Shared meetings need no user mapping; draft isolation must use issuer plus sub, not email.

### Frontend routes, tokens and guest boundary

Use react-oidc-context with oidc-client-ts, not a handwritten OAuth/PKCE implementation. Proposed exact new direct pins, checked against public registry metadata on 8 October 2026:

| Package | Proposed pin | Metadata compatibility |
| --- | --- | --- |
| react-oidc-context | 3.3.1 | Node >=18; React >=16.14.0; peer oidc-client-ts ^3.1.0 accepts 3.5.0. |
| oidc-client-ts | 3.5.0 | Node >=18; typed public API; its jwt-decode dependency is resolved through the frontend lockfile, not manually reimplemented. |
| PyJWT[crypto] | 2.15.1 | Python >=3.9; crypto extra requires cryptography >=3.4.0. |
| cryptography | 50.0.2 | Python >=3.9 excluding 3.9.0/3.9.1; published cp311-abi3 manylinux ARM64 wheels support the pinned Python 3.12/Linux backend. |

Registry sources: https://registry.npmjs.org/react-oidc-context/3.3.1, https://registry.npmjs.org/oidc-client-ts/3.5.0, https://pypi.org/pypi/PyJWT/2.15.1/json and https://pypi.org/pypi/cryptography/50.0.2/json. Declared engine/peer requirements cover existing Node 24.0.0, React 19.3.0 and Python 3.12.10. **This is metadata validation only, not installation, typecheck, build, cryptographic-test or runtime proof.** No dependencies or lockfiles were changed. After human approval, resolve and inspect frozen lockfiles, then run compatibility/quality tests; stop and propose replacement pins if validation fails. Do not silently substitute versions. No unrelated upgrades or router framework are requested.

Proposed changes are limited to app mounting/auth context, App.tsx, typed API client/auth helpers, focused components/tests, styles needed for the welcome/header, and deployment configuration. Do not rewrite existing CRUD/status logic unnecessarily.

- / shows a retro welcome and Sign in to guests. Do not mount the meeting workspace, fetch meeting data or display cached meetings before authentication.
- /login/ starts the library's signinRedirect automatically, creating state and a PKCE verifier before redirecting. Prevent duplicate redirects from StrictMode/render races. Submit this Spry URL, never a copied Cognito authorization URL.
- /auth/callback/ uses the library's callback handling; reject missing/mismatched state, failures and replay. Remove callback code/state parameters from the address bar after successful handling and return to the fixed workspace root.
- Signed-in users see their verified-session email, Sign out and the shared meeting workspace. Both password and Google users use the same UI/API flow.
- Send Authorization: Bearer <access token> on every meeting API request. Never send the ID token as API authorization or place tokens in URLs, builds, logs or screenshots.
- Store OIDC state/verifier and session tokens in sessionStorage rather than persistent localStorage. This storage is accessible to JavaScript, not an HttpOnly/XSS-proof vault; avoid unsafe HTML and never store Google/password secrets there.
- Automatically renew the access token using the library and Cognito refresh token while the session remains valid. Do not rely solely on third-party iframe cookies. A failed renewal/401 must not create a redirect storm or falsely display a signed-in workspace.
- On terminal session loss, clear fetched meetings, pending confirmations and user-visible cached data, invalidate request/mutation generations, and offer sign-in. Late responses from an earlier session cannot repopulate a guest/new-user workspace. Scope deletion tombstones and locks to the session; retain normal within-session race protection.
- Do not automatically replay POST or DELETE after renewal or reauthentication, including operations whose result is uncertain. Distinguish an acknowledged creation from a subsequent refresh failure. Token renewal is not permission to repeat a mutation.
- Sign out clears local OIDC state, meeting state and saved drafts, then redirects to the Cognito /logout endpoint with the public client ID and an exactly allowlisted logout_uri. Do not assume the standard OIDC end-session endpoint exists. Offline JWT verification cannot promise immediate revocation of an already-issued access token; its remaining validity is bounded by expiry.

Add narrow static-route rewriting for /login/ and /auth/callback/ (and deliberate canonical trailing-slash handling). Do not rewrite /api, fingerprinted assets, unknown routes or API 401/404/422/503 into index.html/200. CloudFront API caching stays disabled and Authorization must reach the ALB/backend. Verify the actual forwarding behavior during acceptance.

### Draft recovery

Preserve the human's unfinished title, local start/end strings and attendee-count input during normal errors and token renewal. Before a required reauthentication redirect, save only the draft form fields in a validated sessionStorage record keyed by issuer and Cognito sub. This survives the OAuth page round-trip in the same tab, without becoming a server-side draft or automatically submitting anything.

After login, restore only a record matching that exact issuer/sub. Another account, including a separate Google identity with the same email, must not see or inherit the draft. Explicit Sign out deletes saved drafts. Clear the matching saved draft after acknowledged successful creation, retain failure input, and never persist meetings, confirmation state, credentials or tokens in the draft record. Recovery from an uncertain POST outcome must not silently encourage duplicate creation; reload the server list and explain uncertainty without replaying the request.

### API enforcement and exceptions

In Cognito mode require authentication for GET/POST /api/meetings and DELETE /api/meetings/{meeting_id}, before any meeting storage operation. Use a maintained JWT verifier, not decoding alone. Restrict the signing algorithm to the pool's expected RS256 and validate the cryptographic signature, expiry, expected issuer, token_use=access and exact public client_id. Reject ID tokens, wrong pools/clients, expired/tampered tokens and missing/malformed Bearer credentials with a generic 401; include the Bearer authentication challenge and do not leak validation internals.

Construct the JWKS endpoint from trusted configured pool/region, never caller-provided jku/URLs. Cache keys with a bounded lifetime and bounded refresh on rotation/unknown kid; prevent unbounded network refresh per bad request. Use bounded HTTPS waits. A verifier infrastructure failure is fail-closed and a generic 503, never permission to bypass authentication; ordinary invalid tokens remain 401. Do not confuse authentication-service errors with Database unavailable.

Every valid authenticated user may list, create and delete any meeting. Keep UUIDs, fields, validation, ordering, transactions and successful 200/201/204 plus authorized 404/422/storage-503 contracts unchanged. No migrations or ownership data are needed.

GET /api/health remains unauthenticated for ALB/Compose readiness, with its existing DB-checking response. CORS preflight requires no token and keeps an explicit localhost origin plus Authorization support for local Cognito testing. The human selected publicly readable /api/docs and OpenAPI schema because they document contracts, not meeting data; their Try it out calls still require an access token. These are explicit exceptions, not a public meetings bypass.

Authentication is mandatory and fail-closed **both locally and in production**, as explicitly selected by the human. Missing/partial configuration must stop startup/deployment clearly, not enable an anonymous demo, fake login or development bypass. Local use requires complete public pool issuer, client ID and managed-login domain configuration, supplied from auth-stack outputs through an ignored environment file; no AWS credentials, Google secret or production database password are required to run the app. Register the exact localhost callback/logout URLs and explain this prerequisite in README/.env.example during future implementation. Keep three Compose services and existing local DB startup/migration/readiness behavior; propose loopback-only published ports. Automated tests use signed fixture JWTs and explicit test configuration, never a deployable auth-disable flag.

### Deployment boundaries and acceptance

After future approval, deployment tooling reads public auth-stack outputs into frontend build variables and backend ECS parameters, rather than manual copying. Keep the existing VITE_API_URL=/, clean committed-tree snapshot builds, locks, funding/account guards, secret handling, controlled migration sequence and retained database/assets. Establish/verify the existing frontend hostname, configure Google against the chosen Cognito domain, deploy auth, then a protected backend and authenticated frontend. Coordinate the cutover; do not claim zero downtime. No schema migration or data transfer accompanies this change.

Testing before cloud changes: exact dependency/runtime compatibility; cfn-lint for auth.yaml and amended templates; secret/output and production fail-closed safety tests; signed fixture JWT tests for each rejection case, cache/rotation/network failures and public health; frontend guest-zero-meeting-fetch, redirect/callback/logout, renewal/401, same-user draft recovery, wrong-user isolation and stale-response tests. Retain all CRUD, deletion-race, persistence and live-clock regressions. Do not use valuable application data for tests.

After separately authorized deployment, verify both login methods in fresh/private browser sessions; password signup, email confirmation, sign-out and subsequent sign-in; Google access for an account outside any former test-user list; correct email in the header; protected API calls with access tokens; 401 without a token and rejection of ID tokens; direct /login/ and callback static routing; mobile layout; account still FREE. API/storage and health error semantics must remain JSON and uncached through CloudFront.

Prepare the submission /login/ URL, two actual signed-in site screenshots with email visible (one password, one Google), and a commit link containing auth infrastructure and frontend changes; include stretch implementation and notes answering the assignment's migration/cost/authentication discussion questions. Screenshots/notes go to submission artifacts, not automatically into the public repository. Do not invent users, screenshots, test results, costs or successful publication. LMS submission remains a separate explicit action.
