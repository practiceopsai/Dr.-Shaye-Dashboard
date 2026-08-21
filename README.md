# Eli Command Center

Action-oriented daily command center for Dr. Omid Shaye. The application combines a Next.js dashboard with a FastAPI control plane and connects to the existing Hermes Chief of Staff through the production Orgo vault.

## Architecture

- `frontend/` — Next.js App Router UI.
- `backend/` — FastAPI API, Anthropic priority synthesis, Orgo/Hermes bridge, Composio MCP health, approval ledger.
- Hermes connection — the dashboard reads the same production vault and records feedback/approvals through its governed run lifecycle.
- External actions — only exact, allowlisted tool calls may execute; all others become approval packages for Hermes.

## Local development

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\uvicorn app.main:app --reload --port 8000

cd ..\frontend
npm install
$env:NEXT_PUBLIC_API_URL='http://localhost:8000'
npm run dev
```

## Required backend variables

See `backend/.env.example`. Secrets must be configured in Railway, never committed.

## Safety model

- No practice-account or patient-identifiable data is ingested.
- Every action package includes the exact payload and SHA-256 approval hash.
- Editing a payload invalidates its approval.
- Unsupported actions are queued for Hermes instead of being guessed.
- Aspirational context is a planning tie-breaker, never a factual claim or authorization.

