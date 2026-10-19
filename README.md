# PaceMate

PaceMate is an AI-based personal learning planner. This repository contains the product requirements, mockup, and the 14-day MVP implementation plan.

## Project layout

- `frontend/`: Next.js + TypeScript app
- `backend/`: FastAPI app
- `PRD.md`, `TASK.md`: product requirements and phase-based implementation tasks
- `mockup/index.html`: reference UI mockup

## Requirements

- Node.js 20.9 or later (Node.js 24 LTS is used for this workspace)
- Python 3.11 or later

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

## Reference project

`reference-AI NATIVE M -2/` is a temporary reference copy of a separate project. It is for reading and comparison only; it is excluded from this repository and is not part of PaceMate's source, install, or deployment steps. Remove the folder and its `.gitignore` entry when it is no longer needed. Do not copy its secrets or environment files into this project.

## Secrets

Never commit real credentials. Keep Firebase service-account credentials and the OpenAI API key in local ignored environment files or deployment secret settings. `.env.example` files contain names and safe defaults only.
