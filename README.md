# ReconFlow

ReconFlow is a D2C finance operations application for reconciling order, marketplace settlement, COD, courier freight, and warehouse return data. It preserves imported source records, validates mapped data, runs deterministic Decimal-based comparisons, and tracks evidence and claims for finance review.

## Current status

The source repository is prepared locally. No Git remote is configured, so there is no verified GitHub repository URL yet. Cloud services have not been deployed from this workspace. See [deployment.md](deployment.md) for the verified setup status and deployment runbook.

## Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS, React Router, Axios, Recharts
- Backend: Python, FastAPI, SQLAlchemy, Pandas
- Database: PostgreSQL with Alembic migrations
- Authentication: password hashing and signed JWT bearer tokens
- AI: optional LLM-assisted column mapping suggestions; users approve mappings manually

## Repository layout

```text
backend/       FastAPI app, SQLAlchemy models, migrations, seed tool, tests, benchmark
frontend/      React application and Vite configuration
docs/          Architecture, schema, and API documentation
deployment.md  Vercel, Render, PostgreSQL, environment, seed, and verification guide
render.yaml    Render service and managed PostgreSQL blueprint
```

## Local development

### Backend

From `backend/`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with a local PostgreSQL URL and a random `JWT_SECRET_KEY` of at least 32 characters. Ensure the database exists, then run:

```powershell
# Clear a stale shell override if it points at the wrong database. This makes
# Pydantic read DATABASE_URL from backend/.env in this PowerShell session.
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
alembic upgrade head
python seed.py
uvicorn app.main:app --reload
```

Run each command separately and wait for success before continuing. If you see PowerShell's `>>` continuation prompt, press `Ctrl+C` once to cancel the incomplete command, then enter each command on its own line.

The API listens on `http://localhost:8000`. Interactive API documentation is at `/docs`; health endpoints are `/health` and `/health/ready`.

Create a local finance user interactively (the password is prompted and never placed in shell history):

```powershell
python seed.py --email finance@example.test --full-name "Demo Finance" --role FINANCE_COFOUNDER 
```

To load clearly labeled fictional finance records after creating the user, run:

```powershell
python seed.py --email finance@example.test --demo-data

```

### Frontend

From `frontend/`:

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

Set `VITE_API_BASE_URL=http://localhost:8000/api` in `.env.local`. Build with `npm run build`.

### Backend checks

From `backend/`:

```powershell
python -m pytest -q
python -m compileall -q app migrations seed.py tests benchmarks
```

## Design and API documentation

- [Technical Design Document](docs/Technical%20Design%20Document.docx)
- [Architecture diagram](docs/architecture.md)
- [Database ER diagram](docs/database-er.md)
- [API endpoint reference](docs/api.md)
- [Deployment guide](deployment.md)
- [Phase 6 quality audit](backend/quality_audit_report.md)

## Financial safety behavior

The reconciliation engine uses `Decimal` in calculations and PostgreSQL `NUMERIC` for monetary storage. The default discrepancy threshold is ₹10. Missing source data is treated as unknown rather than a confirmed loss. GST TCS and income-tax TDS remain separate fields. AI output is limited to mapping suggestions; a finance user must approve a mapping before processing.

## Assumptions and limitations

- The client’s mapping and sample rules remain authoritative; there is no invented partner tariff or claim policy.
- Rate card data is illustrative unless a finance user imports/configures a verified partner tariff.
- Imported source rows are preserved for traceability; selected PII is masked in the import preview.
- No hosted deployment, public URL, GitHub remote, or demo login is verified at this stage.
- The 100,000-row benchmark in the audit used local SQLite and is not a PostgreSQL production benchmark.
- The frontend build and live PostgreSQL/browser integration require a dependency-enabled environment before submission.
