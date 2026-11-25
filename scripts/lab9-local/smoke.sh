#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
evidence="$root/docs/evidence/lab9/local"
image=spry-cloudrun:lab9-local
pg_image=postgres:16.8-bookworm
run="spry-lab9-local-$$"
db="$run-db"
mock="$run-jwks"
api="$run-api"
front_url=http://127.0.0.1:5173
api_url=http://127.0.0.1:8080
issuer_host=cognito-idp.us-east-1.amazonaws.com
export COGNITO_ISSUER="https://$issuer_host/us-east-1_SpryLab9MockOnly"
export COGNITO_CLIENT_ID=SpryLab9LocalClient
if [[ -z "${CHROME_BIN:-}" ]]; then
  CHROME_BIN=$(command -v chromium || command -v google-chrome || true)
  CHROME_BIN=${CHROME_BIN:-'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}
fi
export CHROME_BIN
[[ -x "$CHROME_BIN" ]] || { printf 'Set CHROME_BIN to a Chrome/Chromium executable.\n' >&2; exit 1; }

work=$(mktemp -d)
work=$(cd "$work" && pwd -P)
web_pid=
network_created=
cleanup() {
  local status=$?
  if [[ "$status" != 0 && -f "$work/evidence/smoke.log" ]]; then
    printf '\nSmoke failed; runtime diagnostics:\n' >&2
    tee <"$work/evidence/smoke.log" >&2 || true
  fi
  if [[ -n "$web_pid" ]]; then kill "$web_pid" 2>/dev/null || true; fi
  if [[ -n "$network_created" ]]; then
    docker rm -fv "$api" "$mock" "$db" >/dev/null 2>&1 || true
    docker network rm "$run" >/dev/null 2>&1 || true
  fi
  rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

wait_for() {
  local i
  for ((i = 0; i < 60; i++)); do
    if "$@"; then return 0; fi
    sleep 0.5
  done
  printf 'Timed out waiting for %s\n' "$1" >&2
  return 1
}

mkdir "$work/fixture" "$work/evidence"
# Build dependencies may use public registries. Nothing uses the repo's AWS .env.
docker build -f back/Dockerfile.cloudrun -t "$image" back
# Isolate the frontend build from existing node_modules, dist and .env files.
mkdir "$work/front"
cp -R front/src front/public front/index.html front/package*.json front/tsconfig*.json \
  front/vite.config.ts "$work/front/"
(cd "$work" && npm install --no-save --no-audit --no-fund --ignore-scripts playwright-core@1.58.2)
(
  cd "$work/front"
  npm ci --no-audit --no-fund
  VITE_API_URL="$api_url" VITE_PARSER_URL='' \
  VITE_COGNITO_ISSUER="$COGNITO_ISSUER" VITE_COGNITO_CLIENT_ID="$COGNITO_CLIENT_ID" \
  VITE_COGNITO_DOMAIN=https://spry-lab9.invalid \
    npm run build -- --outDir "$work/site"
)

# Cert is trusted only by this backend container. The issuer-shaped hostname is
# pinned to a Docker-only IP, not a real Cognito connection.
(
  umask 077
  openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=$issuer_host" \
    -addext "subjectAltName=DNS:$issuer_host" \
    -keyout "$work/fixture/tls.key" -out "$work/fixture/tls.crt" 2>"$work/openssl.log" \
    || { >&2 printf 'Unable to create fixture certificate (check OpenSSL supports -addext).\n'; exit 1; }
)
chmod 644 "$work/fixture/tls.crt"

run_demo() {
  printf 'Spry Lab 9 local smoke | '; date -u +%FT%TZ
  docker network create --opt com.docker.network.bridge.enable_ip_masquerade=false "$run" >/dev/null
  network_created=1
  printf 'Dedicated Docker bridge options: '; docker network inspect --format '{{json .Options}}' "$run"
  docker image inspect --format 'Backend image: {{.Id}} {{.Os}}/{{.Architecture}}; user: {{.Config.User}}; command: {{json .Config.Cmd}}' "$image"

  # Local DB credentials only. The data directory is new tmpfs storage per run.
  docker run -d --name "$db" --network "$run" --network-alias db \
    --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=lab9 -e POSTGRES_PASSWORD=lab9-local \
    -e POSTGRES_DB=lab9 "$pg_image" >/dev/null
  db_ready() { docker exec "$db" pg_isready -h 127.0.0.1 -U lab9 -d lab9 >/dev/null; }
  wait_for db_ready
  db_env=(-e DATABASE_URL=postgresql+psycopg://lab9:lab9-local@db:5432/lab9)
  auth_env=(-e COGNITO_ISSUER -e COGNITO_CLIENT_ID)
  printf '\n== Apply Alembic migrations ==\n'
  docker run --rm --network "$run" "${db_env[@]}" "${auth_env[@]}" "$image" alembic upgrade head

  psql() { docker exec -i "$db" psql -X -U lab9 -d lab9 -v ON_ERROR_STOP=1 "$@"; }
  printf '\n== Seed and read PostgreSQL directly ==\n'
  psql -c "INSERT INTO meetings (id, title, starts_at, ends_at, attendee_count)
    VALUES ('15842400-0000-4000-8000-000000000009', 'Lab 9 Cloud Run demo',
    now() + interval '1 day', now() + interval '1 day 30 minutes', 6);"
  psql -c 'SELECT version();' -c 'SELECT version_num FROM alembic_version;' \
    -c 'SELECT id, title, starts_at, ends_at, attendee_count FROM meetings;'
  psql -Atc 'SELECT row_to_json(m) FROM (SELECT id, title, attendee_count FROM meetings) m;' >"$work/seed.json"

  # The mock has no host port; only its public JWKS path is exposed to the API.
  docker run -d --name "$mock" --network "$run" \
    --user "$(id -u):$(id -g)" "${auth_env[@]}" \
    --mount "type=bind,src=$root/scripts/lab9-local/mock-cognito.py,dst=/mock-cognito.py,readonly" \
    --mount "type=bind,src=$work/fixture,dst=/fixture" "$image" python /mock-cognito.py >/dev/null
  if ! wait_for test -s "$work/fixture/session.json"; then docker logs "$mock"; return 1; fi

  mock_ip=$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$mock")
  [[ -n "$mock_ip" ]]
  printf '\n== Run the image default command with PORT=8080 ==\n'
  printf 'Fixture issuer hostname pinned to Docker JWKS container: %s\n' "$mock_ip"
  docker run -d --name "$api" --network "$run" -e PORT=8080 -p 127.0.0.1:8080:8080 \
    --add-host "$issuer_host:$mock_ip" \
    "${db_env[@]}" "${auth_env[@]}" -e CORS_ORIGINS="$front_url" \
    -e SSL_CERT_FILE=/lab9-local-tls.crt -e NO_PROXY='*' -e no_proxy='*' \
    --mount "type=bind,src=$work/fixture/tls.crt,dst=/lab9-local-tls.crt,readonly" "$image" >/dev/null
  docker port "$api" 8080/tcp
  api_ready() { curl --noproxy '*' -fs --max-time 1 "$api_url/api/health" >/dev/null; }
  if ! wait_for api_ready; then docker logs "$api"; return 1; fi
  printf 'Health: '; curl --noproxy '*' -fsS "$api_url/api/health"; printf '\n'
  unauthenticated=$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' "$api_url/api/meetings")
  printf 'GET /api/meetings without a token: HTTP %s\n' "$unauthenticated"
  [[ "$unauthenticated" == 401 ]]

  printf '\n== Load the built frontend in Chromium ==\n'
  python3 -m http.server --bind 127.0.0.1 --directory "$work/site" 5173 >"$work/frontend.log" 2>&1 &
  web_pid=$!
  web_ready() { kill -0 "$web_pid" && curl --noproxy '*' -fs --max-time 1 "$front_url/" >/dev/null; }
  wait_for web_ready
  if ! node scripts/lab9-local/browser.mjs "$work" "$work/evidence"; then
    docker logs "$api"; docker logs "$mock"; return 1
  fi

  printf '\n== Uvicorn access log ==\n'
  docker logs "$api" 2>&1
  printf '\n== Local Cognito mock access log ==\n'
  docker logs "$mock" 2>&1
}

# Redirect directly: a pipeline would put the Docker cleanup state in a subshell.
run_demo >"$work/evidence/smoke.log" 2>&1
mkdir -p "$evidence"
cp "$work/evidence/"* "$evidence/"
printf 'Screenshot and verification saved to %s\n' "$evidence"
