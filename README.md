# Eli Command Center

Action-oriented daily command center for Dr. Omid Shaye. The application combines a Next.js dashboard with a FastAPI control plane and connects to the existing Eli Agent through the production Orgo vault.

## Freshness and current Eli state

The dashboard reads the current approved character, confirmed preference files, user model, familiarity stage, autonomy ledgers, memory health, messaging status, and scheduled-job counts from production. It shows their observation times and source revisions. Historical CURRENT_STATUS timelines and persona example rewrites are not used as today's work. Transient briefing, log, and interaction evidence older than 36 hours is excluded; standing confirmed preferences can remain valid longer.

Every brief expires after five minutes and at the next midnight in Dr. Shaye's timezone. Expired actions are hidden. A failed synthesis returns an explicit unavailable state with no invented fallback tasks. The frontend checks for fresh data every minute while visible, on foreground, and on network recovery. With BACKGROUND_REFRESH_ENABLED=true, the backend prepares each new day's brief even when neither phone is open, refreshes while in use, and retries unavailable integrations. Source dates and partial-coverage warnings remain visible: a fresh synthesis does not prove every underlying real-world fact is current.

Gmail and Calendar are verified through account-pinned reads, including bounded pagination and smaller pages when the connector substitutes a preview. Provider configuration alone never counts as a successful connection. Personal-account responses are reduced to safe metadata before synthesis.

Pending internal feedback and voice writeback use SQLite when DASHBOARD_STATE_PATH is set. Production must mount persistent storage at that path. A bounded background worker retries these records; direct external-action approvals remain short-lived and are not replayed after restart. Operator feedback is attributed to the authenticated operator and cannot become a preference attributed to Dr. Shaye.

Production publishes through the existing Railway workflow after backend tests, frontend tests, and a production build pass. See [the TestFlight/iPhone plan](docs/IPHONE-PLAN.md) for native distribution and the distinction between live server updates and signed app updates.

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
