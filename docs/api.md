# ReconFlow API Reference

Base prefix: `/api`; JSON APIs use bearer JWT authentication except `POST /auth/login`. Health checks are outside the prefix. Finance roles are `FINANCE_EXECUTIVE` and `FINANCE_COFOUNDER`; routes marked co-founder require `FINANCE_COFOUNDER`.

| Method and path | Access | Purpose |
|---|---|---|
| `GET /health` | Public | Liveness check |
| `GET /health/ready` | Public | Readiness check including database connectivity |
| `POST /api/auth/login` | Public | Validate credentials and issue access token |
| `GET /api/auth/me` | Authenticated | Return current user and role names |
| `GET /api/admin/roles` | Co-founder | List role definitions |
| `GET /api/admin/users` | Co-founder | Read-only user directory (no credentials) |
| `GET /api/partners` | Finance | List partners |
| `POST /api/partners` | Co-founder | Create partner |
| `POST /api/imports/upload` | Finance | Upload CSV/XLSX (`file`, `partner_id`, `report_type` form fields) |
| `GET /api/imports` | Finance | Filter and page imports |
| `GET /api/imports/{import_id}` | Finance | Read import status and metadata |
| `GET /api/imports/{import_id}/preview` | Finance | Read masked 20-row preview |
| `POST /api/imports/{import_id}/approve` | Finance | Approve and version a column mapping |
| `POST /api/imports/{import_id}/apply-template` | Finance | Apply a saved mapping version to an import |
| `POST /api/imports/{import_id}/validate` | Finance | Validate mapped rows |
| `POST /api/imports/{import_id}/process` | Finance | Persist validated financial rows |
| `POST /api/mappings/suggest` | Finance | Get AI/demo column mapping suggestions; no automatic save/approval |
| `GET /api/mappings` | Finance | List saved templates, optional partner/report type filters |
| `GET /api/mappings/{template_id}/versions` | Finance | List mapping history |
| `POST /api/mappings/{template_id}/rollback` | Finance | Create a rollback mapping version |
| `POST /api/reconciliation/run` | Finance | Run on import IDs or supplied reconciliation records |
| `GET /api/reconciliation/runs/{run_id}` | Finance | Read run summary |
| `GET /api/reconciliation/results?run_id=...` | Finance | Filter and page run results |
| `GET /api/reconciliation/results/{result_id}` | Finance | Read result and explanation |
| `GET /api/rate-cards` | Finance | List rate cards |
| `POST /api/rate-cards` | Co-founder | Create rate card and history snapshot |
| `PUT /api/rate-cards/{rate_card_id}` | Co-founder | Create a revised rate card version |
| `POST /api/rate-cards/{rate_card_id}/deactivate` | Co-founder | Deactivate a rate card |
| `POST /api/rate-cards/{rate_card_id}/activate` | Co-founder | Activate a rate card |
| `GET /api/rate-cards/{rate_card_id}/history` | Finance | Read rate card version history |
| `GET /api/returns` | Finance | Filter and page returns; can filter overdue |
| `GET /api/returns/{return_id}` | Finance | Read return and warehouse evidence |
| `GET /api/claims` | Finance | Filter/page claims by partner/status/category |
| `GET /api/claims/export` | Finance | Export claim evidence as CSV |
| `GET /api/claims/{claim_id}` | Finance | Read claim detail/evidence/notes |
| `PATCH /api/claims/{claim_id}/status` | Finance | Update claim status, recovery, reviewer |
| `POST /api/claims/{claim_id}/notes` | Finance | Add internal claim note |
| `GET /api/reports/money-at-risk` | Finance | Database-backed exposure, recovery, status and age aggregates |
| `GET /api/audit-logs` | Co-founder | Filter and page audit events |

Request and response schemas are defined in `backend/app/schemas/`. The running API's OpenAPI schema at `/openapi.json` is the executable contract. This reference does not list every query parameter or field; inspect OpenAPI for exact request validation details.
