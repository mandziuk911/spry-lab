**Lab 9 no-GCP-account route:** this is the local Cloud Run-style app demo, not a cloud deployment.

## Evidence

- [Browser screenshot](spry-local.png): the built Spry frontend displaying the seeded **Lab 9 Cloud Run demo** meeting.
- [Browser API capture](browser-api-read.json): the frontend document and its live `GET http://127.0.0.1:8080/api/meetings` both returned HTTP 200. The test compares the returned meeting ID, title and attendee count to a direct PostgreSQL query and checks that the title is visible.
- [Smoke log](smoke.log): Docker image command and port, Alembic migrations, PostgreSQL version and row, HTTP 401 without a token, and Uvicorn and fixture JWKS access logs.

## Reproduce

From the repository root, run `./scripts/lab9-local/smoke.sh`. It needs Docker with BuildKit, a Node.js/npm version supported by Vite, Python 3, OpenSSL with `req -addext`, Chrome/Chromium (`CHROME_BIN` if not auto-detected), and free loopback ports 5173 and 8080. Docker and package installs may fetch public build dependencies. The smoke uses a fresh PostgreSQL 16 container and runs `alembic upgrade head` as a separate container before starting the API. It removes the demo containers, temporary database, network, frontend server and transient credentials on exit.

The backend uses the default command from `back/Dockerfile.cloudrun`: Uvicorn serving plain HTTP on `0.0.0.0:$PORT`, without a Lambda adapter. The evidence records the local image architecture. To target Cloud Run, build for Linux x86-64, e.g. `docker build --platform linux/amd64 -f back/Dockerfile.cloudrun -t spry-cloudrun back`.

**Auth simulation:** the browser starts with a short-lived fixture session in its own session storage; hosted Cognito sign-in, refresh and logout are not tested. The API still validates the signed access token as usual. The synthetic issuer hostname is pinned to a one-run Docker JWKS container and the backend is given the fixture's TLS certificate. The fixture is not part of the backend image, does not expose credentials, and is not a production auth mode. No requests are made to AWS, and no real user data or credentials appear in the artifacts.
