import asyncio
import re
import secrets
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .integrations import ComposioMCPClient, EliAgentClient
from .models import ApprovalRequest, DashboardPayload, ExecuteRequest, FeedbackRequest, FeedbackResponse, VoiceIntent, VoiceRequest, VoiceResponse
from .priorities import build_dashboard
from .outbox import PendingMap
from .phone_preview import router as phone_preview_router
from .security import AuthUser, contains_phi, payload_hash, require_auth


settings = get_settings()


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_refresh_loop()) if settings.background_refresh_enabled else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="Eli Command Center API", version="1.1.0", lifespan=lifespan)
app.include_router(phone_preview_router)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

_cache: dict[str, Any] = {}
_approvals: dict[str, dict[str, Any]] = {}
_pending_feedback = PendingMap(settings.dashboard_state_path, "feedback",
    encode=lambda value: [value[0].model_dump(), value[1]], decode=lambda value: (FeedbackRequest.model_validate(value[0]), value[1]))
_pending_voice = PendingMap(settings.dashboard_state_path, "voice", decode=tuple)
_actors = PendingMap(settings.dashboard_state_path, "actors")
_writeback_lock = asyncio.Lock()
_refresh_lock = asyncio.Lock()
_last_viewed: datetime | None = None


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, private"
    return response


def _cache_current(payload: DashboardPayload, now: datetime) -> bool:
    local = ZoneInfo(settings.dashboard_timezone)
    return bool(payload.expires_at and now < payload.expires_at
                and payload.generated_at.astimezone(local).date() == now.astimezone(local).date())


async def _refresh_dashboard(force: bool = False) -> DashboardPayload:
    async with _refresh_lock:
        now = datetime.now(timezone.utc)
        cached = _cache.get("dashboard")
        if cached and _cache_current(cached[1], now) and (not force or now - cached[0] < timedelta(seconds=15)):
            return cached[1]
        payload = await build_dashboard(settings)
        _cache["dashboard"] = (datetime.now(timezone.utc), payload)
        return payload


async def _refresh_loop():
    while True:
        try:
            now = datetime.now(timezone.utc)
            cached = _cache.get("dashboard")
            zone = ZoneInfo(settings.dashboard_timezone)
            new_day = not cached or cached[1].generated_at.astimezone(zone).date() != now.astimezone(zone).date()
            viewed = _last_viewed and now - _last_viewed < timedelta(minutes=10)
            # Prepare the new day's brief even with no open phones. While in use,
            # keep it fresh; avoid hundreds of unused model calls overnight.
            retry_needed = cached and not all(cached[1].integrations.values())
            if new_day or viewed or retry_needed:
                await _refresh_dashboard()
            async with _writeback_lock:
                await _flush_pending_feedback()
                await _flush_pending_voice()
        except Exception:
            logging.getLogger("eli.refresh").exception("Background refresh failed")
        await asyncio.sleep(60)

_PRIORITY_VOICE_TERMS = re.compile(
    r"\b(priority|priorities|important|urgent|rank|ranking|daily brief|not relevant|not useful|useful|prefer|preference|show less|show more|protect time)\b",
    re.I,
)
_DASHBOARD_VOICE_TERMS = re.compile(
    r"\b(dashboard|command center|widget|calendar|schedule|layout|display|screen|section|button|interface|ui)\b",
    re.I,
)


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
    if feedback_id not in _pending_feedback:
        return True
    actor = _actors.get(feedback_id, {"label": "Unverified dashboard user", "owner": False})
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
    if not actor["owner"]:
        summary = summary.replace("Dr. Shaye", actor["label"])
        detail = detail.replace("Dr. Shaye said:", actor["label"] + " said:")
        learnings, memory_candidates = [], []
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
    _actors.pop(feedback_id, None)
    _cache.pop("dashboard", None)
    return True


async def _flush_pending_feedback(limit: int = 1) -> None:
    for feedback_id, (request, item_context) in list(_pending_feedback.items())[:limit]:
        if not await _deliver_feedback(feedback_id, request, item_context):
            break


def _voice_intent(transcript: str) -> VoiceIntent:
    if _PRIORITY_VOICE_TERMS.search(transcript):
        return "priority_feedback"
    if _DASHBOARD_VOICE_TERMS.search(transcript):
        return "dashboard_change"
    return "action_request"


async def _deliver_voice(command_id: str, transcript: str, intent: VoiceIntent) -> bool:
    if command_id not in _pending_voice:
        return True
    actor = _actors.get(command_id, {"label": "Unverified dashboard user", "owner": False})
    if intent == "priority_feedback":
        workflow = "daily-briefing"
        summary = "Priority guidance received through Talk to Eli"
        memory_candidates = [f"Candidate priority preference reported directly by Dr. Shaye: {transcript}"]
    elif intent == "dashboard_change":
        workflow = "commitment-capture"
        summary = "Dashboard improvement requested through Talk to Eli"
        memory_candidates = []
    else:
        workflow = "commitment-capture"
        summary = "Action requested through Talk to Eli"
        memory_candidates = []
    detail = f"Talk to Eli command {command_id} | intent: {intent} | Dr. Shaye said: {transcript}"
    if not actor["owner"]:
        detail = detail.replace("Dr. Shaye said:", actor["label"] + " said:")
        memory_candidates = []
    try:
        await EliAgentClient(settings).record(
            workflow,
            summary,
            [detail],
            memory_candidates=memory_candidates,
            mode="user_requested_unapproved",
        )
    except Exception:
        return False
    _pending_voice.pop(command_id, None)
    _actors.pop(command_id, None)
    _cache.pop("dashboard", None)
    return True


async def _flush_pending_voice(limit: int = 1) -> None:
    for command_id, (transcript, intent) in list(_pending_voice.items())[:limit]:
        if not await _deliver_voice(command_id, transcript, intent):
            break


def _voice_reply(intent: VoiceIntent, recorded: bool) -> str:
    if not recorded:
        return "I heard you. Your request is safely queued and I will retry it when the command center refreshes."
    if intent == "priority_feedback":
        return "I recorded that as priority guidance. I will use it when rebuilding your daily brief."
    if intent == "dashboard_change":
        return "I recorded that as a tracked dashboard improvement and sent it to Eli for implementation."
    return "I captured that action request with Eli. Any external action will still require your exact approval before it runs."


@app.get("/health")
async def health():
    cached = _cache.get("dashboard")
    return {"status": "ok", "service": "eli-api", "version": app.version,
            "time": datetime.now(timezone.utc).isoformat(), "background_refresh_enabled": settings.background_refresh_enabled,
            "persistent_writeback": bool(settings.dashboard_state_path),
            "last_refresh_verified": cached[1].live if cached else None,
            "last_refresh_at": cached[0].isoformat() if cached else None}


@app.get("/api/auth/me")
async def auth_me(user: AuthUser = Depends(require_auth)):
    return {
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "role": user.role,
    }


@app.get("/api/status", dependencies=[Depends(require_auth)])
async def status():
    payload = await _refresh_dashboard()
    return {
        "status": "ok" if payload.live else "degraded",
        "checked_at": payload.generated_at,
        "integrations": payload.integrations,
        "eli": payload.eli,
        "live_actions_enabled": settings.live_actions_enabled,
        "pending_feedback": len(_pending_feedback),
        "pending_voice": len(_pending_voice),
    }


@app.get("/api/dashboard", response_model=DashboardPayload, dependencies=[Depends(require_auth)])
async def dashboard(refresh: bool = False) -> DashboardPayload:
    global _last_viewed
    _last_viewed = datetime.now(timezone.utc)
    return await _refresh_dashboard(force=refresh)


@app.post("/api/feedback", response_model=FeedbackResponse, dependencies=[Depends(require_auth)])
async def feedback(req: FeedbackRequest, user: AuthUser = Depends(require_auth)):
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
    _actors[feedback_id] = {"label": "Dr. Shaye" if user.role == "owner" else f"Fabio/operator ({user.email})", "owner": user.role == "owner"}
    _pending_feedback[feedback_id] = (req, item_context)
    async with _writeback_lock:
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
    async with _writeback_lock:
        if feedback_id not in _pending_feedback:
            raise HTTPException(404, "Feedback was already recorded")
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


@app.post("/api/voice", response_model=VoiceResponse, dependencies=[Depends(require_auth)])
async def voice(req: VoiceRequest, user: AuthUser = Depends(require_auth)) -> VoiceResponse:
    if contains_phi(req.transcript):
        raise HTTPException(422, "Voice command may contain clinical or patient-identifiable content")
    transcript = req.transcript.strip()
    intent = _voice_intent(transcript)
    command_id = f"voice_{secrets.token_hex(8)}"
    _actors[command_id] = {"label": "Dr. Shaye" if user.role == "owner" else f"Fabio/operator ({user.email})", "owner": user.role == "owner"}
    _pending_voice[command_id] = (transcript, intent)
    async with _writeback_lock:
        recorded = await _deliver_voice(command_id, transcript, intent)
    _cache.pop("dashboard", None)
    return VoiceResponse(
        command_id=command_id,
        status="recorded" if recorded else "queued",
        intent=intent,
        message=_voice_reply(intent, recorded),
        eli_agent_writeback=recorded,
        retriable=not recorded,
        next_brief_refresh=True,
    )
