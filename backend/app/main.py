import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .integrations import ComposioMCPClient, OrgoHermesClient, integration_health
from .models import ApprovalRequest, ExecuteRequest, FeedbackRequest, VoiceRequest
from .priorities import build_dashboard
from .security import contains_phi, payload_hash, require_auth


settings = get_settings()
app = FastAPI(title="Eli Command Center API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

_cache: dict[str, Any] = {}
_approvals: dict[str, dict[str, Any]] = {}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "eli-api", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/status", dependencies=[Depends(require_auth)])
async def status():
    return {"status": "ok", "integrations": await integration_health(settings), "live_actions_enabled": settings.live_actions_enabled}


@app.get("/api/dashboard", dependencies=[Depends(require_auth)])
async def dashboard(refresh: bool = False):
    cached = _cache.get("dashboard")
    if cached and not refresh and datetime.now(timezone.utc) - cached[0] < timedelta(minutes=10):
        return cached[1]
    payload = await build_dashboard(settings)
    _cache["dashboard"] = (datetime.now(timezone.utc), payload)
    return payload


@app.post("/api/feedback", dependencies=[Depends(require_auth)])
async def feedback(req: FeedbackRequest):
    if contains_phi(req.feedback):
        raise HTTPException(422, "Feedback may contain clinical or patient-identifiable content and was not stored")
    detail = f"Dashboard item {req.item_id}: {req.disposition} — {req.feedback}"
    try:
        await OrgoHermesClient(settings).record("daily-briefing", "Dashboard feedback recorded", [detail])
        recorded = True
    except Exception:
        recorded = False
    _cache.pop("dashboard", None)
    return {"status": "recorded" if recorded else "deferred", "hermes_writeback": recorded}


@app.post("/api/approvals", dependencies=[Depends(require_auth)])
async def approve(req: ApprovalRequest):
    serialized = req.item.model_dump(mode="json")
    if contains_phi(str(serialized)):
        raise HTTPException(422, "Action package may contain clinical or patient-identifiable content")
    approval_id = secrets.token_urlsafe(18)
    digest = payload_hash(serialized)
    _approvals[approval_id] = {"hash": digest, "item": serialized, "approved_at": datetime.now(timezone.utc), "expires": datetime.now(timezone.utc) + timedelta(minutes=15), "used": False}
    return {"approval_id": approval_id, "payload_hash": digest, "expires_in_seconds": 900, "exact_action": serialized["action"]}


@app.post("/api/execute", dependencies=[Depends(require_auth)])
async def execute(req: ExecuteRequest):
    approval = _approvals.get(req.approval_id)
    if not approval or approval["used"] or approval["expires"] < datetime.now(timezone.utc):
        raise HTTPException(409, "Approval is missing, expired, or already used")
    if not secrets.compare_digest(req.payload_hash, approval["hash"]) or payload_hash(approval["item"]) != approval["hash"]:
        raise HTTPException(409, "The action changed after approval")
    approval["used"] = True
    item = approval["item"]
    action = item["action"]
    # Generic LLM instructions are never converted directly into external calls.
    # They are durable, exact approval packages that Hermes can safely pick up.
    if action["kind"] != "composio" or not settings.live_actions_enabled:
        detail = f"APPROVED via dashboard: {item['title']} | exact action: {action['label']} | approval hash: {approval['hash']}"
        try:
            await OrgoHermesClient(settings).record("commitment-capture", "Dashboard action approved and queued for Hermes", [detail])
            return {"status": "queued_for_hermes", "approval_hash": approval["hash"]}
        except Exception as exc:
            approval["used"] = False
            raise HTTPException(503, f"Hermes queue unavailable: {type(exc).__name__}")
    if contains_phi(str(action.get("arguments", {}))):
        approval["used"] = False
        raise HTTPException(422, "Approved action may contain clinical or patient-identifiable content")
    client = ComposioMCPClient(settings)
    try:
        clean_arguments = client.validate_write(action.get("tool_name") or "", action.get("arguments") or {})
    except ValueError as exc:
        approval["used"] = False
        raise HTTPException(422, str(exc))

    # From this point the approval remains consumed. A transport failure can be
    # ambiguous after a write, so the system must never retry it automatically.
    try:
        result = await client.execute_allowlisted(action.get("tool_name") or "", clean_arguments)
    except Exception as exc:
        raise HTTPException(502, f"Action outcome is unknown; approval consumed to prevent duplicates: {type(exc).__name__}")

    detail = f"EXECUTED via dashboard: {item['title']} | tool: {result['tool']} | approval hash: {approval['hash']} | resource: {result.get('resource_id') or 'created'}"
    try:
        await OrgoHermesClient(settings).record("commitment-capture", "Dashboard action executed through Composio", [detail])
        writeback = True
    except Exception:
        writeback = False
    return {"status": "executed", "approval_hash": approval["hash"], "result": result, "hermes_writeback": writeback}


@app.post("/api/voice", dependencies=[Depends(require_auth)])
async def voice(req: VoiceRequest):
    if contains_phi(req.transcript):
        raise HTTPException(422, "Voice command may contain clinical or patient-identifiable content")
    return {"status": "parsed", "message": "Voice transcript captured. Confirm actions individually before execution.", "transcript": req.transcript}
