import json
import logging
import re
import asyncio
from datetime import datetime
from anthropic import AsyncAnthropic
from .config import Settings
from .integrations import ComposioMCPClient, OrgoHermesClient, integration_health
from .models import ActionSpec, DashboardPayload, PriorityCard


SYSTEM = """You are Eli, Dr. Omid Shaye's action-oriented Chief of Staff dashboard.
Return JSON only. Select no more than three true high-value priorities plus at most three short administrative items.
Use P0 immediate crisis, P1 same-day critical, P2 deadline/decision, P3 strategic important, P4 routine.
Place each in: now (act today), protect (important-not-urgent focus), delegate (someone is blocked/routine), monitor (watch/defer).
Protect family, Shabbat/Yom Tov, prayer/Torah, health, high-value clinical work, and strategic deep work.
Never include PHI, patient names, clinical details, or facts supported only by aspiration. Do not guess stale facts.
The loudest sender is not automatically the highest priority.
Every card needs a concrete outcome and action. Generic external actions must use kind=hermes_queue. Never invent a Composio tool name.
Schema: {greeting:string, focus:string, cards:[{id,priority,lane,category,title,context,consequence,deadline,source,mission_alignment,action:{label,kind:'hermes_queue',tool_name:null,arguments:{},account:'personal',recipients:[],reversible:true}}]}"""

logger = logging.getLogger("eli.priorities")


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("Model returned no JSON object")
    return json.loads(match.group(0))


def _normalize_card(item: dict) -> dict:
    """Fail safe on model schema drift without broadening action authority."""
    normalized = dict(item)
    if normalized.get("priority") not in {"P0", "P1", "P2", "P3", "P4"}:
        normalized["priority"] = "P4"
    if normalized.get("lane") not in {"now", "protect", "delegate", "monitor"}:
        normalized["lane"] = "monitor"
    if normalized.get("mission_alignment") not in {"aligned", "mixed", "tension", "unknown"}:
        normalized["mission_alignment"] = "unknown"
    action = normalized.get("action") if isinstance(normalized.get("action"), dict) else {}
    normalized["action"] = {
        "label": str(action.get("label") or "Ask Hermes to prepare the next step"),
        "kind": "hermes_queue",
        "tool_name": None,
        "arguments": {},
        "account": "personal",
        "recipients": [],
        "reversible": True,
    }
    return normalized


def fallback_cards() -> list[PriorityCard]:
    return [
        PriorityCard(id="refresh-connections", priority="P2", lane="now", category="System", title="Confirm today's operating picture", context="Live priority synthesis is temporarily unavailable. Refresh the Hermes and Composio connections before acting on stale context.", consequence="The dashboard may miss a new deadline or commitment.", source="system health", mission_alignment="unknown", action=ActionSpec(label="Ask Hermes to refresh the daily brief")),
        PriorityCard(id="protected-focus", priority="P3", lane="protect", category="Focus", title="Protect one important, non-urgent outcome", context="Reserve focused time for family, Torah, health, healing, teaching, relationship repair, or strategic work.", consequence="Urgency will otherwise displace high-value work.", source="priority-and-escalation policy", mission_alignment="aligned", action=ActionSpec(label="Ask Hermes to propose a focus block")),
    ]


async def build_dashboard(settings: Settings) -> DashboardPayload:
    health = await integration_health(settings)
    warnings: list[str] = []
    cards: list[PriorityCard]
    live = False
    try:
        context, signal_result = await asyncio.gather(
            OrgoHermesClient(settings).context(),
            ComposioMCPClient(settings).personal_signals(),
            return_exceptions=True,
        )
        if isinstance(context, Exception):
            raise context
        if not context.strip():
            raise RuntimeError("Hermes returned no context")
        if isinstance(signal_result, Exception):
            warnings.append(f"Personal inbox/calendar signals unavailable: {type(signal_result).__name__}")
            signals = "No fresh personal inbox or calendar signals were available."
        else:
            signals = signal_result or "No relevant personal inbox or calendar signals were found."
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.anthropic_model,
            # Sonnet 5 may spend part of this budget on internal reasoning before
            # emitting the JSON dashboard; 2,400 could end with no text block.
            max_tokens=6000,
            system=SYSTEM,
            messages=[{"role":"user","content":f"Today is {datetime.now().astimezone().isoformat()}. Build the dashboard from the sources below. Vault material may be stale. Personal signals are metadata only and may be incomplete. Cite either the vault file/heading or personal inbox/calendar in source.\n\n--- HERMES VAULT ---\n{context}\n\n--- PERSONAL SIGNALS (NO MESSAGE BODIES OR EVENT DESCRIPTIONS) ---\n{signals}"}],
        )
        parsed = _extract_json("".join(block.text for block in message.content if hasattr(block, "text")))
        cards = []
        for item in parsed.get("cards", []):
            try:
                cards.append(PriorityCard.model_validate(_normalize_card(item)))
            except Exception:
                logger.warning("Skipping one malformed priority card", exc_info=True)
        cards = cards[:6]
        if not cards:
            raise ValueError("Model returned no valid priority cards")
        greeting = parsed.get("greeting", "Good morning, Dr. Shaye.")
        focus = parsed.get("focus", "Protect attention for what matters most.")
        live = bool(cards and health.get("hermes") and health.get("anthropic"))
    except Exception as exc:
        logger.exception("Live priority synthesis failed")
        cards = fallback_cards()
        greeting = "Good morning, Dr. Shaye."
        focus = "Live synthesis needs attention; showing safe standing priorities."
        warnings.append(f"Live synthesis unavailable: {type(exc).__name__}")
    if not health.get("composio"):
        warnings.append("Composio is offline; external actions will remain queued.")
    if not health.get("hermes"):
        warnings.append("Hermes/Orgo is offline; vault write-back is unavailable.")
    return DashboardPayload(generated_at=datetime.now().astimezone(), live=live, greeting=greeting, focus=focus, cards=cards, admin_count=sum(c.priority == "P4" for c in cards), integrations=health, warnings=warnings)
