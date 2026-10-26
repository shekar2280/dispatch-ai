# Testing Dispatch AI

## Local checks without accounts

Install the API development requirements and the web dependencies, then run from the repository root:

```sh
python -m pytest
npm run lint
npm run typecheck
npm run build:smoke
npx --prefix apps/web playwright install chromium
npm run test:smoke
```

The browser smoke configuration starts its own production web server on port 3100 using `.next-smoke`, separate from a development server’s `.next` directory. It covers public navigation, protected-route redirects, form validation, password visibility, authentication transport failure, mobile layout, and security headers. It requires a completed web build but no database, staging account, backend, or paid provider. Build with placeholder public Supabase configuration to keep the run independent of your deployment; CI shows the exact variables.

Backend tests disable dotenv loading, use synthetic voice token credentials, and block network connections unless marked as integration tests. LiveKit package imports are still needed, so install all development requirements. The default run excludes `live` and `voice_db` tests.

## Test organization

The public suite contains 19 backend test modules and 8 browser specification files, plus shared fixtures and authentication setup.

| Area | Coverage |
| --- | --- |
| Security and patients | Authentication, clinic isolation, patient identity, notes, and clinical-data redaction |
| Booking and clinic operations | Capacity, schedules, walk-ins, queues, consultations, and billing |
| Voice | Call routing, consent, audio, provider error handling, usage, settings, and cleanup |
| PostgreSQL | Concurrent reservations, settlement, permissions, migrations, and payment races |
| Browser | Public authentication, clinician workflows, receptionist operations, failures, and role/tenant access |

Real-provider and load experiments are maintained privately. Their omission does not remove the isolated voice regression tests or the public database concurrency tests.

## Disposable PostgreSQL tests

These tests check the current schema, concurrent bookings and allowance reservations, idempotent settlement, retention, and voice-credit permissions. Use a new database called exactly `dispatch_voice_tests` on localhost. Its application tables will be dropped and recreated. No Supabase account is required: the fixture supplies minimal auth schema objects.

```sh
docker run --rm -d --name dispatch-tests -e POSTGRES_DB=dispatch_voice_tests -e POSTGRES_PASSWORD=local-test-only -p 127.0.0.1:55439:5432 postgres:16-alpine
```

From PowerShell at the repository root, with your virtual environment active:

```powershell
$env:VOICE_TEST_DATABASE_URL = 'postgresql://postgres:local-test-only@127.0.0.1:55439/dispatch_voice_tests'
Set-Location apps/api
python -m pytest -o addopts='' -m voice_db tests/test_voice_postgres.py
Set-Location ../..
docker stop dispatch-tests
```

The CI PostgreSQL job uses the same tests against an ephemeral service container.

## Staging browser journeys

The main `playwright.config.ts` is separate from smoke testing. Its default journeys use genuine staging sessions and can create patients, visits, notes, and payment receipts. Use a dedicated clinic with fictional records, configured hours, available future capacity, and distinct doctor, receptionist, administrator, and second-tenant accounts.

From `apps/web`, copy `e2e/environment.example` to `.env.e2e` and fill in its variables. The file is ignored by Git. Existing shell variables take precedence. Keep the web app, API, and Redis running. No service role credential belongs in the browser test environment.

```sh
npx playwright test --list
npx playwright test --project=public
npx playwright test --project=receptionist
npx playwright test --project=doctor
npx playwright test --project=admin
npx playwright test --project=cashier
npx playwright test --project=security
```

The `doctor` project also needs receptionist credentials for its cross-browser case; `cashier` needs doctor and receptionist; `security` needs doctor, receptionist, and Clinic B. Authentication setup writes private session state to `playwright/.auth`. Missing staging configuration is an error, not a successful test run.

Fault tests marked `@fault` deliberately fail network requests or return error responses. They verify error handling; they do not establish provider availability. API-assisted setup and assertions are identified in test names.

### Recorded-call playback

- Set `E2E_RUN_RECORDING=1` and the recording variables in the example file for authorized real-recording playback.

The public tree keeps clinic workflow and payment concurrency integrations. Real-provider and load experiments are kept outside the public tree.

Python tests marked `live` additionally require `RUN_LIVE_TESTS=1`, an explicit `TEST_DATABASE_URL` with `test` in its database name, and staging service credentials supplied through the shell. Dotenv files are never loaded by pytest. `TEST_ORG_ID`, `TEST_STAFF_USER_ID`, and `TEST_DOCTOR_ID` select existing synthetic accounts for clinic integration tests. Run only the relevant files:

```sh
python -m pytest -o addopts='' -m live apps/api/tests/integration apps/api/tests/test_security.py apps/api/tests/test_call_routing.py
```

## Artifacts and limits

Playwright reports, traces, screenshots, videos, and auth state are ignored. They may contain account/session details: share sanitized failures only. Fixture teardown cancels tracked visits when their state allows it; completed encounters, patient profiles, payments, and recordings can remain in staging for reviewed cleanup.

Local smoke tests do not establish authenticated workflow correctness. Staging tests do not establish clinical safety, regulatory compliance, carrier reliability, all browser/device behavior, or unlimited concurrency. Revalidate OAuth, invite/revoke lifecycle, storage expiry, WebSocket/process restarts, timezones/DST, accessibility, and provider failures separately.
