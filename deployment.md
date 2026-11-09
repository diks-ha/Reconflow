# ReconFlow Deployment Guide

## Verified deployment status

No GitHub remote is configured, no Vercel or Render CLI/account connection is available in the workspace, and no hosted application or database URL has been verified. Therefore no deployed URLs or demo credentials are published here. The configuration below is prepared for deployment after the repository is pushed to a GitHub account connected to Vercel and Render.

## Deployment topology

- Vercel builds and serves the Vite single-page frontend from `frontend/`.
- Render runs the FastAPI service from `backend/` and hosts managed PostgreSQL.
- `render.yaml` describes the Render API service, database, migration command, health check, and persistent upload disk. Render's `fromDatabase` reference injects the database connection string, and the app normalizes PostgreSQL URI schemes to the installed psycopg v3 driver.
- `frontend/vercel.json` rewrites SPA paths to `index.html`.

Render Blueprints support managed Postgres references, generated secrets, and pre-deploy migration commands as configured here ([Blueprint reference](https://render.com/docs/blueprint-spec)). Render requires the pre-deploy feature to be supported by the selected paid web service plan. Confirm the current plan and charges in Render before provisioning.

## 1. Push the repository to GitHub

This local checkout has no GitHub remote or commit history. Create or select a repository in your GitHub account, then from the project root:

```powershell
git add .
git status --short
git commit -m "Prepare ReconFlow submission"
git remote add origin https://github.com/<your-account>/<your-repository>.git
git push -u origin main
```

Before committing, confirm `.env`, `.env.local`, upload storage, test storage, virtual environments, `node_modules`, and build output are ignored. `.env.example` files are intentionally included and contain placeholders only. Do not commit live API keys, database URLs with passwords, JWT secrets, or demo passwords. Add the repository URL to the top of the TDD after GitHub has confirmed it.

## 2. Create Render API and PostgreSQL

1. Connect the GitHub repository to Render.
2. Create a new Blueprint instance from the repository root (`render.yaml`). Review service and database plan/cost before applying it.
3. Set `CORS_ORIGINS` on the API service to a JSON string containing the exact deployed frontend origin, for example `["https://your-verified-project.vercel.app"]` after Vercel provides the real URL. Do not use a guessed origin.
4. Render generates `JWT_SECRET_KEY` and supplies `DATABASE_URL` from the managed database. The service sets `APP_ENV=production`, `UPLOAD_DIR=/var/data/uploads`, and `MAX_UPLOAD_SIZE_MB=50`.
5. If using live LLM mapping suggestions, add `LLM_API_KEY` in the Render dashboard secret store. Leaving it unset selects deterministic demo suggestions.
6. The service deploy command runs `alembic upgrade head`. Wait for `/health/ready` to return `{"status":"ready","database":"ok"}`.

Required backend environment variables:

| Name | Value/source | Secret? |
|---|---|---|
| `DATABASE_URL` | Render managed PostgreSQL internal connection string | Yes |
| `JWT_SECRET_KEY` | Generated random secret, at least 32 characters | Yes |
| `APP_ENV` | `production` | No |
| `CORS_ORIGINS` | JSON array with the verified Vercel origin | No |
| `UPLOAD_DIR` | `/var/data/uploads` persistent disk mount | No |
| `MAX_UPLOAD_SIZE_MB` | `50` by default | No |
| `LLM_API_KEY` | Optional LLM provider key | Yes |
| `LLM_BASE_URL` | Optional provider API base URL | No |
| `LLM_MODEL` | Optional configured suggestion model | No |

## 3. Deploy frontend on Vercel

1. Import the GitHub repository in Vercel.
2. Set **Root Directory** to `frontend`.
3. Use build command `npm run build` and output directory `dist`.
4. Set `VITE_API_BASE_URL` to the actual Render service URL with `/api`, for example `https://<verified-render-host>/api` only after it is assigned. This variable is embedded into the frontend at build time.
5. Deploy. Vercel environment variable changes require a new deployment ([Vercel environment variables](https://vercel.com/docs/environment-variables)); SPA route handling is configured in `frontend/vercel.json` ([Vercel rewrites](https://vercel.com/docs/routing/rewrites)).
6. Update Render `CORS_ORIGINS` with Vercel's exact production origin and redeploy the API.

Frontend environment:

| Name | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://<verified-render-host>/api` |

## 4. Create an account and seed demo data

There is no preconfigured demo password in the codebase and no seeded hosted user is verified. The seed tool prompts interactively for a password (minimum 12 characters, maximum 72 UTF-8 bytes); it does not embed a fixed password. Do not put a password on the command line or in this file.

After connecting to the deployed service shell with the configured backend environment and database, create the demo account and fictional sample records in one command. Use a test email you control and enter a unique password at the prompt:

```sh
python seed.py --email <demo-email-you-control> --full-name "ReconFlow Demo" --role FINANCE_COFOUNDER --demo-data
```

The seed tool creates illustrative website, marketplace, courier, rate-card, order, settlement, COD, freight, and return data, then runs reconciliation. It is idempotent for the included sample order IDs. Verify the account and login before handing over access.

**Demo login details for the final submission:** email is the operator-supplied account from this command; password is the private value entered at the prompt. Record these details in the final handoff only after the account and login have been verified. Do not publish a shared default password in source control.

## 5. Verify the deployed app

After both services are deployed and configured, record and verify the actual URLs, then run:

1. Open `https://<verified-frontend-host>/` and confirm the login screen renders.
2. Request `https://<verified-render-host>/health`; expect HTTP 200 and `{"status":"ok"}`.
3. Request `https://<verified-render-host>/health/ready`; expect HTTP 200 and database readiness.
4. Log in with the created demo account; confirm `/api/auth/me` returns its expected role.
5. Verify protected dashboard queries load from real API data.
6. Upload a small sample CSV/XLSX, approve a mapping, validate, process, and reconcile it.
7. Verify claims/returns and export behavior with seeded or imported data.
8. Confirm a second role's restrictions (or unauthenticated rejection) with API requests.
9. Capture final deployment URLs, the verified test time, and the demo account email for submission. Never record the password in repository files.

Until these steps are performed against the actual deployed services, the application should be described as **prepared for deployment, not deployed or verified**.
