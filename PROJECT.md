# Spry — repository specification

Status: draft for human review. This commit contains the specification only. Do not generate application code until this document is approved.

## Repository decision

Spry is a monorepo: backend, frontend, database configuration and, in a later stage, CI and deployment configuration share one repository. API and client changes can be reviewed and committed atomically. An agent can read the endpoint, schema, migration and UI together instead of guessing contracts across repositories. For a small team building the first slice, shared context is worth more than independent repositories and release cycles.

The course source is https://github.com/dobosevych/OneTwoThree. This personal private copy preserves its Git history. Keep that repository as the upstream remote; push personal work only to the personal origin. Grant the lecturer access to this repository before submission.

The course source already includes back/, front/, compose.yaml, infra/ and a Makefile. The proposed layout below differs from that source and is not an instruction to overwrite or duplicate those files. Before generation, review the inherited implementation and amend this draft with an explicit retain/rename/replace decision. Existing course code is inherited, not generated from this specification; it has not yet been verified against the contracts below.

## Scope and exclusions

The first slice lists and creates meetings through a single frontend page backed by PostgreSQL. Only three Compose services exist: postgres, backend and frontend.

Do not add authentication, attendee records, editing, deletion, pagination, analytics, Redis, Celery, a reverse proxy, a second database, Kubernetes or AWS resources in this stage. Attendee count is a stored integer, not a relationship to users. Do not invent week-over-week statistics. Styling against the Lab 1 reference images is a later review step when those images are supplied.

CI, linters and AWS deployment are required later in the lab, but their configuration must be specified and reviewed in a subsequent revision before implementation. This initial specification covers local structure only.

## Pinned baseline

These are deliberate reproducible baseline choices, not claims about the latest releases. Verify package compatibility before implementation; propose any changes to this document for review rather than silently substituting versions.

| Component | Version |
| --- | --- |
| Backend base image | python:3.12.10-slim-bookworm |
| PostgreSQL image | postgres:16.8-bookworm |
| Frontend base image | node:22.14.0-bookworm-slim |
| FastAPI | 0.115.12 |
| Uvicorn | 0.34.2 |
| SQLAlchemy | 2.0.40 |
| Alembic | 1.15.2 |
| Psycopg binary driver | 3.2.6 |
| Pydantic | 2.11.3 |
| React and React DOM | 19.0.0 |
| Vite | 6.2.6 |
| Vite React plugin | 4.4.1 |
| TypeScript | 5.8.3 |
| Tailwind CSS and its Vite plugin | 4.1.3 |
| shadcn CLI (generation only) | 2.5.0 |

shadcn/ui components are committed source files, not a runtime service or a monolithic library dependency. Use only the button, input, label and card primitives needed for this page. Pin every additional direct dependency needed by those components to an exact version in package.json and commit package-lock.json; installation uses npm ci. Backend dependencies, including transitive dependencies, belong in a committed exact-version requirements.txt. No latest tags or floating dependency ranges.

## Repository structure

The following is the intended layout after approval and generation, not a claim that these files already exist.

| Path | Purpose and boundary |
| --- | --- |
| PROJECT.md | Reviewed source of truth for structure and contracts. |
| README.md | Startup command, local URLs, prerequisites and troubleshooting; distinguish development defaults from production configuration. |
| .gitignore | Exclude secrets, local environment overrides, virtual environments, node_modules, build outputs and editor artifacts. |
| docker-compose.yml | Coordinate the three local services, configuration, ports, readiness and the database volume. |
| backend/ | Python API and database migrations; does not contain frontend code. |
| backend/Dockerfile | Build a runnable API image; no database connection or migration during image build. |
| backend/requirements.txt | Exact Python runtime and transitive dependency pins. |
| backend/alembic.ini | Alembic configuration; database URL comes from the environment, not a committed production credential. |
| backend/app/ | Backend Python package; package marker files have no business logic. |
| backend/app/main.py | Assemble FastAPI, allowed origins and routes. |
| backend/app/config.py | Read and validate environment configuration. |
| backend/app/db.py | SQLAlchemy engine, session lifecycle and declarative base; request-scoped sessions. |
| backend/app/api/ | HTTP routes for meetings and health; status codes and request/response adaptation, not database schema definitions. |
| backend/app/models/ | SQLAlchemy meeting table mapping and database constraints. |
| backend/app/schemas/ | Pydantic creation and response contracts and input validation. |
| backend/app/services/ | Meeting listing and creation, transaction boundaries and storage-error translation; no HTTP request parsing. |
| backend/alembic/ | Versioned schema history and migration environment. |
| backend/alembic/versions/ | Initial meetings-table migration with upgrade and downgrade operations. |
| frontend/ | Single-page React client and its build configuration; no database access. |
| frontend/Dockerfile | Install locked dependencies and run the local Vite server. |
| frontend/package.json | Exact direct dependency pins and development/build scripts. |
| frontend/package-lock.json | Reproducible frontend dependency resolution. |
| frontend/index.html | Vite HTML entry point. |
| frontend/vite.config.ts | React and Tailwind integration, server binding and port. |
| frontend/tsconfig*.json | TypeScript configuration for application and build tooling. |
| frontend/src/ | Client application source. |
| frontend/src/main.tsx | Mount React and import styles. |
| frontend/src/App.tsx | Assemble the meeting list and creation form on one page. |
| frontend/src/components/ | Meeting list and creation form; loading, empty, error and submitting states. |
| frontend/src/components/ui/ | Only the required committed shadcn/ui primitives. |
| frontend/src/lib/ | Typed API client and utilities required by the UI primitives; no business database logic. |
| frontend/src/styles.css | Tailwind import and shared visual tokens. |

Do not introduce empty placeholder directories. Every generated directory must have one of the purposes above.

## Service and readiness contracts

Docker Desktop with Compose v2 is the only local prerequisite. A clean checkout starts with docker compose up; docker compose up --build explicitly rebuilds images after changes. No host Python, Node, manual migration, environment-file copying or manual database setup is required.

| Service | Listen address and published port | Dependencies and readiness |
| --- | --- | --- |
| postgres | Container TCP 5432; no host port published | No upstream dependency. Health check uses pg_isready with the configured database/user: interval 5s, timeout 5s, start period 10s, retries 12. |
| backend | 0.0.0.0:8000; host 8000 maps to 8000 | Wait for postgres with depends_on condition service_healthy. At container start run alembic upgrade head, then Uvicorn. Migration failure prevents API startup. Health check calls /api/health using Python's standard library: interval 5s, timeout 5s, start period 20s, retries 12. |
| frontend | 0.0.0.0:5173; host 5173 maps to 5173 | Wait for backend with depends_on condition service_healthy. Run Vite with a strict port. Vite binding makes it reachable from the host browser. |

Local addresses are http://localhost:5173 for the frontend and http://localhost:8000 for the backend. Compose service names resolve only inside the Compose network; the browser must call localhost:8000, not backend:8000.

Postgres owns a named volume mounted at /var/lib/postgresql/data. Compose restart/down must preserve meetings; docker compose down -v intentionally removes them. Database schema changes belong to Alembic, never Base.metadata.create_all(). No seed data is required: the first list is empty until a meeting is created.

Local Compose supplies explicit development-only POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, DATABASE_URL, CORS_ORIGINS and VITE_API_BASE_URL defaults. Use database spry and development-only user/password spry/spry; backend DATABASE_URL uses the postgres hostname and Psycopg driver. CORS allows exactly http://localhost:5173. VITE_API_BASE_URL is http://localhost:8000. Local overrides are optional and ignored by Git. No real credentials or production secrets are committed. VITE-prefixed settings are public browser configuration, never secrets.

Compose images use the declared base versions; each application service builds its own Dockerfile. Keep initial setup simple: source is copied into the images rather than bind-mounted, so application changes require a rebuild. The frontend development server, local passwords, published API port and local origins are development-only choices, not a production deployment recipe.

Readiness is not permanent availability. Enable SQLAlchemy pool_pre_ping. If Postgres disappears later, database-backed requests fail promptly with HTTP 503 and a generic detail message; transactions roll back, server logs retain diagnostics and no credentials or SQL internals are exposed to clients. Do not automatically retry a creation request because its transaction outcome may be uncertain. New requests can succeed again after connectivity returns. Frontend errors must be visible rather than appearing as empty successful results.

## Database and API contract

A meeting has exactly these public fields:

| Field | Type and rules |
| --- | --- |
| id | Positive integer generated by the database; clients cannot choose it. |
| title | String, trim surrounding whitespace, length 1–200 after trimming. |
| starts_at | Timezone-aware ISO 8601 timestamp; an offset or Z is mandatory. |
| ends_at | Timezone-aware ISO 8601 timestamp; strictly later than starts_at. |
| attendee_count | Integer greater than or equal to zero; not a boolean or numeric string. |

Store times as PostgreSQL timestamp with time zone and serialize API responses in UTC with Z. The database enforces non-null fields, positive duration and nonnegative attendee count. The initial migration creates only the meetings table and these constraints. SQLAlchemy defines the matching mapping; Alembic owns schema changes.

### GET /api/meetings

Return HTTP 200 with an application/json array of meeting objects containing exactly the five fields above. No envelope, pagination or extra fields. Return an empty array if no meetings exist. Sort by starts_at ascending, then id ascending for a deterministic tie-breaker.

### POST /api/meetings

Accept application/json with exactly title, starts_at, ends_at and attendee_count. All four fields are required; unknown fields, including id, are rejected. Validate the rules above before writing. Commit exactly one row and return HTTP 201 with its complete meeting object, including the generated id. Invalid input returns HTTP 422 using FastAPI's standard validation-error detail array. There is no authentication or duplicate-title prohibition in this slice.

### GET /api/health

This is the only supporting endpoint beyond the meetings contract. It performs a lightweight database check. Return HTTP 200 with status equal to ok when the database is reachable; otherwise HTTP 503 with a generic detail message. It must not disclose connection details. It is used for local readiness and can later support an ALB health check.

The frontend API client mirrors these field names and response shapes. The browser never talks to PostgreSQL. The HTTP layer validates schemas, the service layer coordinates ORM work and transactions, and the model layer represents the table.

## Frontend interaction contract

One page shows a heading, meeting list and creation form. Each listed meeting shows its title, start, end and attendee count. Render timestamps in the browser's local timezone and make that timezone clear.

The form contains title, local start/end datetime inputs and attendee count. Convert local datetime input values to UTC ISO 8601 timestamps before sending; reject invalid dates, nonpositive duration and invalid counts. Backend validation remains authoritative.

Initial page load fetches the list. Show loading, empty and error states distinctly. During creation disable duplicate submission. After HTTP 201 reset the form and fetch the ordered list again. If creation succeeds but the refresh fails, report that distinction rather than telling the user creation failed. Failed requests preserve form input and present readable errors. Do not automatically retry POST requests.

## Review and local acceptance gate

Before code generation, the human reviewer checks folder purposes, exclusions, exact pins, date/count contracts and health-based startup ordering. Amend this specification before implementing any changed decision.

After generation, verify:

- A clean checkout starts with docker compose up --build without manual setup.
- PostgreSQL becomes healthy before migrations; migrations run before API serving.
- Frontend startup waits for backend readiness.
- GET /api/meetings initially returns an empty array on a fresh volume.
- Creating a valid meeting returns HTTP 201 and it appears in the frontend.
- Reloading the page and restarting Compose preserve the meeting.
- Invalid titles, naive timestamps, invalid duration and negative counts return HTTP 422 without creating rows.
- Database unavailability produces HTTP 503 and a visible client error rather than a successful empty list.
- No application code, infrastructure or real secrets are added before this draft is approved.
