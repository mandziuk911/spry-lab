# Spry — reviewed structure before implementation

**Status: minimal-slice implementation authorized by the human after selecting “Follow the lab scope” and requesting continuation.** This document specifies the target, not a claim that the inherited application already complies. Validate the implementation against the acceptance gate below.

## 1. Repository decision

Use one monorepo for the API, frontend, database migrations, local orchestration and CI/deployment configuration. Atomic commits keep API and client contracts together. More importantly, the repository is the agent's context window: it can inspect the endpoint, model, migration and consuming component together. Separate repositories buy release independence but cost shared context. For this small team and first product slice, context is worth more.

Source: https://github.com/dobosevych/OneTwoThree. Personal private copy: https://github.com/mandziuk911/spry. Preserve source Git history, keep the source as `upstream`, and push personal work only to `origin`. Give the lecturer access before submission.

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
| infra/ | Inherited infrastructure source; review/adapt for the required AWS architecture later. No provisioning during local setup. |
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
- Retro redesign renders at desktop and mobile widths without losing focus visibility or overflowing content.
- Only three Compose services exist; only the specified meeting routes and supporting health/docs routes remain active, without authentication.

## 9. Later lab stages — not local implementation scope yet

After local acceptance: match supplied Spry screenshots; run Ruff, ESLint and Prettier locally and in Actions on every push; demonstrate a deliberate red lint commit on a temporary branch.

Review AWS account security, costs and database hosting before provisioning. The assignment leaves production PostgreSQL hosting unspecified: propose RDS and obtain approval rather than silently creating a billable database.

Required later deployment: private S3 through CloudFront for the frontend; commit-SHA-tagged ECR image on ECS Fargate behind an HTTPS ALB for the backend; own app/api domains and ACM certificates; GitHub OIDC trust restricted to this repository and main; green checks gate deployment using the same Makefile targets as local deploys. CloudFront certificate is in us-east-1; ALB certificate is in its region. Define controlled production migrations, rollback and teardown before deployment.

Submission: accessible personal repository, screenshot of frontend meeting list, and reachable HTTPS frontend/backend URLs on the user's domain. No AWS access keys in source or GitHub secrets.
