import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .integrations import ComposioMCPClient, EliAgentClient, integration_health
from .models import ApprovalRequest, ExecuteRequest, FeedbackRequest, FeedbackResponse, VoiceRequest
from .priorities import build_dashboard
from .security import contains_phi, payload_hash, require_auth


settings = get_settings()
app = FastAPI(title="Eli Command Center API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

_cache: dict[str, Any] = {}
_approvals: dict[str, dict[str, Any]] = {}
_pending_feedback: dict[str, tuple[FeedbackRequest, str]] = {}


def _feedback_destination(req: FeedbackRequest) -> tuple[str, str]:
    if req.category == "dashboard_change":
        return "commitment-capture", "Dashboard improvement requested by Dr. Shaye"
    if req.category == "positive_reinforcement":
        return "daily-briefing", "Dashboard priority judgment reinforced by Dr. Shaye"
    return "daily-briefing", "Dashboard priority correction submitted by Dr. Shaye"


def _feedback_item_context(req: FeedbackRequest) -> str:
    if not req.item_id or not (cached := _cache.get("dashboard")):
        return ""
    dashboard_payload = cached[1]
    cards = dashboard_payload.cards if hasattr(dashboard_payload, "cards") else dashboard_payload.get("cards", [])
    for card in cards:
        value = card.model_dump(mode="json") if hasattr(card, "model_dump") else card
        if value.get("id") != req.item_id:
            continue
        context = " | ".join(
            f"{label}: {str(value.get(field) or '').strip()[:240]}"
            for label, field in (("title", "title"), ("priority", "priority"), ("lane", "lane"), ("category", "category"), ("source", "source"))
            if value.get(field)
        )
        return "" if contains_phi(context) else context
    return ""


async def _deliver_feedback(feedback_id: str, req: FeedbackRequest, item_context: str = "") -> bool:
    workflow, summary = _feedback_destination(req)
    association = f" | item: {req.item_id}" if req.item_id else " | dashboard-wide"
    disposition = f" | disposition: {req.disposition}" if req.disposition else ""
    item_detail = f" | {item_context}" if item_context else ""
    detail = f"Feedback {feedback_id} | category: {req.category}{association}{disposition}{item_detail} | Dr. Shaye said: {req.feedback}"
    learning_context = f" Regarding {item_context}." if item_context else ""
    learnings = [f"Reported reinforcement from Dr. Shaye: {req.feedback}{learning_context}"] if req.category == "positive_reinforcement" else []
    preference_context = f" Item context: {item_context}." if item_context else ""
    disposition_context = f" Disposition: {req.disposition}." if req.disposition else ""
    memory_candidates = [f"Candidate priority preference reported by Dr. Shaye: {req.feedback}{disposition_context}{preference_context}"] if req.category == "priority_correction" else []
    try:
        await EliAgentClient(settings).record(
            workflow,
            summary,
            [detail],
            learnings=learnings,
            memory_candidates=memory_candidates,
        )
    except Exception:
        return False
    _pending_feedback.pop(feedback_id, None)
    return True


async def _flush_pending_feedback(limit: int = 1) -> None:
    for feedback_id, (request, item_context) in list(_pending_feedback.items())[:limit]:
        if not await _deliver_feedback(feedback_id, request, item_context):
            break


@app.get("/health")
async def health():
    return {"status": "ok", "service": "eli-api", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/status", dependencies=[Depends(require_auth)])
async def status():
    return {
        "status": "ok",
        "integrations": await integration_health(settings),
        "live_actions_enabled": settings.live_actions_enabled,
        "pending_feedback": len(_pending_feedback),
    }


@app.get("/api/dashboard", dependencies=[Depends(require_auth)])
async def dashboard(refresh: bool = False):
    if _pending_feedback:
        await _flush_pending_feedback()
    cached = _cache.get("dashboard")
    if cached and not refresh and datetime.now(timezone.utc) - cached[0] < timedelta(minutes=10):
        return cached[1]
    payload = await build_dashboard(settings)
    _cache["dashboard"] = (datetime.now(timezone.utc), payload)
    return payload


@app.post("/api/feedback", response_model=FeedbackResponse, dependencies=[Depends(require_auth)])
async def feedback(req: FeedbackRequest):
    if contains_phi(req.feedback):
        raise HTTPException(422, "Feedback may contain clinical or patient-identifiable content and was not stored")
    if req.item_id and (cached := _cache.get("dashboard")):
        dashboard_payload = cached[1]
        cards = dashboard_payload.cards if hasattr(dashboard_payload, "cards") else dashboard_payload.get("cards", [])
        valid_ids = {card.id if hasattr(card, "id") else card.get("id") for card in cards}
        if req.item_id not in valid_ids:
            raise HTTPException(422, "The associated dashboard item is no longer available")
    item_context = _feedback_item_context(req)
    feedback_id = f"feedback_{secrets.token_hex(8)}"
    _pending_feedback[feedback_id] = (req, item_context)
    recorded = await _deliver_feedback(feedback_id, req, item_context)
    _cache.pop("dashboard", None)
    if recorded:
        detail = "Dashboard improvement request recorded with Eli as tracked work." if req.category == "dashboard_change" else "Feedback recorded with Eli and applied to the next priority brief."
    else:
        detail = "Feedback is safely queued. Eli will retry it when the command center refreshes."
    return FeedbackResponse(
        feedback_id=feedback_id,
        status="recorded" if recorded else "queued",
        eli_agent_writeback=recorded,
        retriable=not recorded,
        next_brief_refresh=True,
        detail=detail,
    )


@app.post("/api/feedback/{feedback_id}/retry", response_model=FeedbackResponse, dependencies=[Depends(require_auth)])
async def retry_feedback(feedback_id: str):
    pending = _pending_feedback.get(feedback_id)
    if not pending:
        raise HTTPException(404, "Queued feedback was not found or was already recorded")
    req, item_context = pending
    recorded = await _deliver_feedback(feedback_id, req, item_context)
    return FeedbackResponse(
        feedback_id=feedback_id,
        status="recorded" if recorded else "queued",
        eli_agent_writeback=recorded,
        retriable=not recorded,
        next_brief_refresh=True,
        detail="Feedback recorded with Eli and applied to the next priority brief." if recorded else "Eli is still unavailable; the feedback remains safely queued.",
    )


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
    # They are durable, exact approval packages that Eli Agent can safely pick up.
    if action["kind"] != "composio" or not settings.live_actions_enabled:
        detail = f"APPROVED via dashboard: {item['title']} | exact action: {action['label']} | approval hash: {approval['hash']}"
        try:
            await EliAgentClient(settings).record("commitment-capture", "Dashboard action approved and queued for Eli Agent", [detail])
            return {"status": "queued_for_eli_agent", "approval_hash": approval["hash"]}
        except Exception as exc:
            approval["used"] = False
            raise HTTPException(503, f"Eli Agent queue unavailable: {type(exc).__name__}")
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
        await EliAgentClient(settings).record("commitment-capture", "Dashboard action executed through Composio", [detail])
        writeback = True
    except Exception:
        writeback = False
    return {"status": "executed", "approval_hash": approval["hash"], "result": result, "eli_agent_writeback": writeback}


@app.post("/api/voice", dependencies=[Depends(require_auth)])
async def voice(req: VoiceRequest):
    if contains_phi(req.transcript):
        raise HTTPException(422, "Voice command may contain clinical or patient-identifiable content")
    return {"status": "parsed", "message": "Voice transcript captured. Confirm actions individually before execution.", "transcript": req.transcript}
