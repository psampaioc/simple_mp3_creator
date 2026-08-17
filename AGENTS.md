# Simple MP3 Creator agent rules

## Deployment is the source of truth

This project is already published. Treat the deployed Vercel site and its deployed FastAPI API as the runtime under test.

Do not start, call, or depend on any local backend or media runtime while working on this project:

- do not run FastAPI on `localhost:8000`;
- do not use `DATA_BACKEND=local` for an application flow;
- do not use the SQLite/local filesystem project flow as a substitute for the hosted system;
- do not run `backend/worker` locally;
- do not generate test audio locally as part of the product flow.

Local frontend development, if needed for a visual-only change, must use the deployed API URL through an explicit `NEXT_PUBLIC_API_URL`. Never add a `localhost` fallback. If that variable is absent, fail with a user-facing temporary-unavailability state instead of trying another endpoint.

## Production architecture

The only supported hosted generation path is:

1. The Vercel frontend calls the deployed FastAPI API.
2. The API uses Supabase Auth, Postgres, RLS, and private Storage.
3. The API creates the project/job and dispatches `.github/workflows/media-worker.yml` with `workflow_dispatch`.
4. GitHub Actions runs the media worker once, claims the specific Supabase job, generates the MP3, uploads the private asset, and records the final status.

GitHub Actions is the media worker; it is not the browser API. The browser must never call Actions directly, and the API must never fall back to local background tasks in production.

Required hosted invariants:

- frontend: `NEXT_PUBLIC_API_URL` points to the deployed FastAPI API;
- backend: `APP_ENV=production` and `DATA_BACKEND=supabase`;
- backend: `GITHUB_ACTIONS_TOKEN`, `GITHUB_REPOSITORY`, and `GITHUB_WORKER_WORKFLOW` are configured;
- Supabase contains the job-claim migrations, including the specific-job claim migration;
- the Actions workflow has the Supabase secrets required by `backend/worker`.

## Validation and delivery

Validate with source-level tests/builds and the deployed Vercel/Supabase/GitHub states. Do not declare success because a local API or local worker worked. Check that:

- the public frontend bundle contains no `localhost` API fallback;
- the Vercel frontend and API deployments are successful;
- Supabase migrations, RLS tables, and job states are healthy;
- the GitHub Actions media-worker workflow is available and recent runs are successful.

Keep changes on a working branch, commit after validation, push, open a non-draft PR, and wait for explicit approval before merging or promoting production configuration.
