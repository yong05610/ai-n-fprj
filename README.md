# PaceMate

PaceMate is an AI-based personal learning planner. This repository contains the product requirements, mockup, and the 14-day MVP implementation plan.

## Project layout

- `frontend/`: Next.js + TypeScript app
- `backend/`: FastAPI app
- `PRD.md`, `TASK.md`: product requirements and phase-based implementation tasks
- `mockup/index.html`: reference UI mockup

## Requirements

- Node.js 20.9 or later (Node.js 24 LTS is used for this workspace)
- Python 3.12 (`.python-version`; the versions in `backend/requirements.txt` are pinned and checked on 3.12)

## Run locally

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn main:app --reload --port 8001 --env-file .env
```

The API health endpoint is `http://localhost:8001/health`; Swagger UI is `http://localhost:8001/docs`.

### Frontend

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend reads `NEXT_PUBLIC_API_BASE_URL`; configure `CORS_ORIGINS` on the backend to include the exact frontend origin.

### Auth modes

The example env files run in **dev mode** (`AUTH_MODE=dev` / `STORE_BACKEND=memory` on the backend, `NEXT_PUBLIC_AUTH_MODE=dev` on the frontend), so the consent → anonymous UID flow works without Firebase credentials. Data is kept in backend memory and reset on restart. For real Firebase Anonymous Auth and Firestore, set `AUTH_MODE=firebase`, `STORE_BACKEND=firestore`, `FIREBASE_SERVICE_ACCOUNT_JSON`, and the `NEXT_PUBLIC_FIREBASE_*` values. Firestore rules and indexes live in `firebase/`. See `docs/phase3_auth.md`.

### Tests

```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest
```

`requirements.txt` is what a deployment installs (direct dependencies pinned with `==`); `requirements-dev.txt` adds pytest and the HTTP client the tests use.

### Deployment settings (Render, backend)

When the `RENDER` variable is set, the app refuses to start with `AUTH_MODE=dev`, `STORE_BACKEND=memory`, a missing or unsafe `CORS_ORIGINS` (no `*`, no localhost, https only, no trailing `/`, no empty entry), or an empty `FIREBASE_SERVICE_ACCOUNT_JSON` / `OPENAI_API_KEY`. The message names the rule or variable, never the value. `API_DOCS_ENABLED=false` turns `/docs`, `/redoc` and `/openapi.json` off (default: on). See `docs/deploy_guide.md`.

## Reference project

`reference-AI NATIVE M -2/` is a temporary reference copy of a separate project. It is for reading and comparison only; it is excluded from this repository and is not part of PaceMate's source, install, or deployment steps. Remove the folder and its `.gitignore` entry when it is no longer needed. Do not copy its secrets or environment files into this project.

## Secrets

Never commit real credentials. Keep Firebase service-account credentials and the OpenAI API key in local ignored environment files or deployment secret settings. `.env.example` files contain names and safe defaults only.
