# Lab 9: Spry on Google Cloud

**No-account route:** This Terraform root was initialized and validated locally. No Google Cloud or HCP resources were created, and no billing was enabled. See [validation evidence](evidence/terraform-local.txt).

## Reproduce the local check

```sh
cd gcp
terraform fmt -check -recursive
terraform init -backend=false -input=false -no-color
terraform validate -no-color
terraform test -no-color                 # mocked providers, no GCP requests
```

No `terraform.tfvars`, credentials, HCP login or GCP project is needed. Do not run a live `terraform plan` or `apply` for the no-account submission. `init` downloads providers from the public Terraform registry; it does not contact GCP. The sibling `infra/` root and its state are independent.

## Future live deployment only

The following steps were **not** executed. Use a dedicated, existing GCP project and obtain explicit billing approval first. A budget alert is not a spending cap. The Cloud SQL instance starts incurring charges as soon as it is provisioned.

### 1. Bootstrap the identities and state

A project administrator enables `serviceusage.googleapis.com` and `iam.googleapis.com`, creates `spry-lab9-tf` and `spry-lab9-runtime` service accounts, and grants the following **in the dedicated lab project only**. This small bootstrap stays outside the application root so the Terraform identity does not need permission to edit the project-wide IAM policy or manage service accounts.

| Principal | Role | Scope / reason |
| --- | --- | --- |
| `spry-lab9-tf` | `roles/run.admin` | Lab project; create/manage Cloud Run and the service's invoker rules |
| `spry-lab9-tf` | `roles/cloudsql.admin` | Lab project; manage instance, user and database |
| `spry-lab9-tf` | `roles/artifactregistry.admin` | Lab project; create/manage the registry |
| `spry-lab9-tf` | `roles/secretmanager.admin` | Lab project; create/version the secret and manage its policy |
| `spry-lab9-tf` | `roles/serviceusage.serviceUsageAdmin` | Lab project; enable the four application APIs |
| `spry-lab9-tf` | `roles/iam.serviceAccountUser` | On `spry-lab9-runtime` only; attach that identity to Cloud Run |
| `spry-lab9-runtime` | `roles/cloudsql.client` | Lab project (Cloud SQL connector access) |
| `spry-lab9-runtime` | `roles/secretmanager.secretAccessor` | Only `spry-lab9-database-url`; granted by this root |
| Image publisher | `roles/artifactregistry.writer` | Only the `spry-lab9` repository; grant after creation |
| Named testers (optional) | `roles/run.invoker` | Only the Cloud Run service; pass via `cloud_run_invokers` |

Use no Owner/Editor grants for these identities, no default compute account, and no service-account keys. The Cloud Run service agent pulls images from the same-project registry; the runtime account does not need a registry role. Avoid inherited broad invoker grants on the project.

- **Local live execution:** use ADC with impersonation: `gcloud auth application-default login --impersonate-service-account=spry-lab9-tf@PROJECT_ID.iam.gserviceaccount.com`. An authorized operator needs `roles/iam.serviceAccountTokenCreator` on **that deploy account only**. Use a local `terraform.tfvars` copied from the example.
- **HCP live execution:** in this directory, copy `cloud.tf.example` to `cloud.tf`, replace the organization, and use the separate `spry-lab9-gcp` workspace with remote execution and manual approvals. Do not reuse the AWS workspace, state, or credentials. The ignored template copy is for a CLI-driven workflow: run from `gcp/`. Put Terraform inputs in that workspace rather than sharing them with AWS. If migrating existing state, migrate only this root's state using `terraform init` and review its migration prompt.
- **HCP keyless auth:** enable IAM Credentials and Security Token Service APIs during bootstrap (`iamcredentials.googleapis.com`, `sts.googleapis.com`). In a dedicated GCP Workload Identity Pool, create an OIDC provider with issuer `https://app.terraform.io`, default provider audience, mapping `google.subject=assertion.sub,attribute.workspace_id=assertion.terraform_workspace_id`, and a condition matching the intended immutable `assertion.terraform_organization_id`, `assertion.terraform_project_id`, and `assertion.terraform_workspace_id`. Grant `roles/iam.workloadIdentityUser` on **`spry-lab9-tf` only** to `principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/attribute.workspace_id/WORKSPACE_ID`. Set workspace environment variables `TFC_GCP_PROVIDER_AUTH=true`, `TFC_GCP_RUN_SERVICE_ACCOUNT_EMAIL=spry-lab9-tf@PROJECT_ID.iam.gserviceaccount.com`, and `TFC_GCP_WORKLOAD_PROVIDER_NAME=projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/providers/PROVIDER_ID`. See [HCP dynamic credentials](https://developer.hashicorp.com/terraform/cloud-docs/workspaces/dynamic-provider-credentials/gcp-configuration).

The generated password is part of the Secret Manager `DATABASE_URL` value, never a Terraform output or variable. Terraform state still contains the generated secret; restrict workspace/state access, protect local state and plan files, and never commit or attach them as evidence.

### 2. Provision the database and publish the app image

1. Initialize the selected backend and review the first plan from `gcp/` with `backend_image_digest` unset. After an approved apply, Artifact Registry and the zonal PostgreSQL 16 Enterprise `db-f1-micro` instance (10 GB SSD) exist. Cloud Run does not start until a digest is set. The instance has a public IP for the Cloud SQL connectors but no authorized networks for direct clients; connectors authenticate with IAM and use encrypted transport.
2. Use `terraform output -raw backend_image_repository` (or the HCP output) to obtain the image repository. Configure Docker for `<region>-docker.pkg.dev` with `gcloud auth configure-docker`, using the repository-scoped publisher identity. From the repository root, build and push `docker buildx build --platform linux/amd64 -f back/Dockerfile.cloudrun -t "$IMAGE:lab9" --push back`, where `IMAGE` is that output. Get the pushed registry digest (for example, `docker buildx imagetools inspect "$IMAGE:lab9"`).
3. For the lab database, use **Alembic migrations against an empty database**, not an Aurora export. An authorized operator can start the [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy) with `cloud-sql-proxy --port 5433 INSTANCE_CONNECTION_NAME`, granting that operator Cloud SQL Client and temporary access to this secret separately from the deploy credentials. For this TCP proxy, use `postgresql+psycopg://spry:PASSWORD@127.0.0.1:5433/spry` instead of the Cloud Run socket DSN. Pass it via a protected environment without printing it or putting the password in shell history. With that `DATABASE_URL` and the public Cognito issuer/client ID in the environment, run `uv run --frozen alembic upgrade head` from `back/`. If the lab SQL user cannot create migration objects, have the database administrator grant it `USAGE, CREATE` on the `spry` database's `public` schema; do not grant project IAM privileges to fix a PostgreSQL privilege issue. For production, separate the SQL migration and runtime users.
4. Set `backend_image_digest` to `sha256:...`, set `cognito_issuer` and `cognito_client_id`, and select any named `cloud_run_invokers`. Review and apply. Cloud Run uses the dedicated runtime identity, the `DATABASE_URL` secret version, and the `/cloudsql` socket mount. It scales down to zero.

### 3. Understand the private API and optional Firebase Hosting

The Cloud Run URL is internet-routable for token-authenticated callers, but **invocation requires IAM**. The root does not grant `allUsers`/`allAuthenticatedUsers` or turn off the invoker check. Test with a named invoker and a Google ID token in `X-Serverless-Authorization`. For a protected app endpoint, also pass the existing Cognito access token in `Authorization: Bearer …`; the tokens serve different purposes.

`firebase.json` is a static SPA config only. If later authorized to use Firebase, register the project/site and its permitted Cognito callback/logout URLs. From `front/` build with `npm ci` and `VITE_API_URL=https://YOUR_APPROVED_API_ORIGIN npm run build`, supplying the public `VITE_COGNITO_ISSUER`, `VITE_COGNITO_CLIENT_ID`, and `VITE_COGNITO_DOMAIN` as build inputs. Copy the contents of `front/dist/` into `gcp/public/`; run `firebase deploy --only hosting --project PROJECT_ID` from `gcp/` only for an approved deployment.

A direct browser request from Firebase Hosting **will not** invoke the private Cloud Run service with only a Cognito token; changing CORS does not grant IAM. No Firebase-to-Run rewrite is included. To connect them later, use an authenticated gateway that can invoke Cloud Run and passes the app token separately, or review a public API design after authentication is migrated and verified. Allow only the exact trusted frontend origin if using cross-origin requests. For this submission, use the local frontend and backend for the DB-read demo. Sign-in, weekly reports/email and agenda parsing remain on AWS; reports do not read the separate GCP database.

### 4. Stop or clean up after a live demo

Set `database_running = false` and apply a reviewed change to stop the instance (activation policy `NEVER`). This does not stop storage or any retained backup/IP charges; DB-backed requests will fail until the instance is restarted. Set `database_running = true`, apply and wait for readiness before the next demo.

For deletion, save any data you are authorized to retain, set `database_deletion_protection = false` and apply to clear both protection flags; then review and run `terraform destroy` **in `gcp/` only**. This does not remove the pre-existing project, bootstrap identities/federation or optional Firebase deployment. Clean up those items separately if they were created for the lab and are no longer needed. APIs remain enabled by design. Check for remaining billable resources and review the billing report later.
