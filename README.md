# Eli Command Center

Action-oriented daily command center for Dr. Omid Shaye. The application combines a Next.js dashboard with a FastAPI control plane and connects to the existing Eli Agent through the production Orgo vault.

## Architecture

- `frontend/` — Next.js App Router UI.
- `backend/` — FastAPI API, Anthropic priority synthesis, Eli Agent bridge, personal-account Composio signals, approval ledger.
- Eli Agent connection — the dashboard reads the same production vault and records feedback/approvals through its governed run lifecycle.
- Priority alignment — every refresh reads Dr. Shaye's current preference files, latest morning brief, latest run log, and BM25 priority/feedback retrievals before synthesis.
- Ownership routing — technology and troubleshooting are deterministically assigned to Fabio in the delegate/monitor lanes, never presented as Dr. Shaye's personal execution work.
- External actions — only exact, allowlisted tool calls may execute; all others become approval packages for Eli Agent.
- Continuous improvement — Dr. Shaye can correct priorities, reinforce good judgment, or request dashboard changes. Feedback is written to Eli Agent, refreshes the next brief, and exposes a safe retry when writeback is temporarily unavailable.

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
- Gmail reads are metadata-only; calendar descriptions and email bodies are never sent to the model.
- Every Composio call is pinned to explicitly configured personal connection IDs.
- Every action package includes the exact payload and SHA-256 approval hash.
- Editing a payload invalidates its approval.
- Unsupported actions are queued for Eli Agent instead of being guessed.
- Direct writes are limited to plain-text Gmail sends and Google Calendar creation, and remain off unless `LIVE_ACTIONS_ENABLED=true`.
- Aspirational context is a planning tie-breaker, never a factual claim or authorization.
