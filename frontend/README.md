# ReconFlow frontend

React, TypeScript and Vite finance workspace connected to the FastAPI backend.

## Local setup

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

The default API URL is `http://localhost:8000/api`. Set `VITE_API_BASE_URL` in `.env` if the backend runs elsewhere. The backend must allow the frontend origin in `CORS_ORIGINS`.

Run `npm run build` for the production build and `npm run preview` to serve that build locally.

The Audit & Users screen is restricted to Finance Co-founders. User accounts and roles are currently read-only because the backend exposes a user directory and role listing but no user provisioning or role mutation endpoints.
