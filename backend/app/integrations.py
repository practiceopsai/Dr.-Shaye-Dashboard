import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
import httpx
from .config import Settings
from .security import contains_phi


class EliAgentClient:
    """Durable bridge to Eli Agent: same production vault, retrieval, and run ledger."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.url = f"https://www.orgo.ai/api/computers/{settings.orgo_computer_id}/exec"

    async def exec(self, code: str, timeout: float = 90) -> dict[str, Any]:
        if not self.settings.orgo_api_key:
            raise RuntimeError("Orgo is not configured")
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self.url,
                json={"code": code},
                headers={"Authorization": f"Bearer {self.settings.orgo_api_key}"},
            )
            response.raise_for_status()
            result = response.json()
        if result.get("exit_code") not in (None, 0):
            raise RuntimeError(f"Eli Agent bridge exited {result.get('exit_code')}: {result.get('stderr', '')[-500:]}")
        return result

    async def context(self) -> str:
        code = r'''
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess,sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
v=Path(r"C:\data\DrShaye\vault")
parts=[]
direct=[
    "CURRENT_STATUS.md",
    "daily-briefing/PLAYBOOK.md",
    "daily-briefing/LEARNINGS.md",
    "design/governance/approval-and-autonomy.md",
    "memory/preferences/daily-organization.md",
    "memory/preferences/time-protection.md",
    "memory/preferences/approval-posture.md",
    "memory/preferences/notification-and-vault-updates.md",
    "memory/preferences/communication-voice.md",
]
for folder in ["briefings/morning", "daily-briefing/logs"]:
    candidates=sorted((v/folder).glob("*.md"), key=lambda p:p.stat().st_mtime, reverse=True)
    if candidates: direct.append(str(candidates[0].relative_to(v)))
for rel in direct:
    p=v/rel
    if p.exists(): parts.append(f"\n--- {rel} ---\n"+p.read_text(encoding="utf-8")[:2500])
queries=[
    "What commitments, deadlines, waiting-on items, and active projects matter now?",
    "What are Omid's current daily priority rules and protected-time rules?",
    "What current preferences and standing feedback has Omid given Eli Agent about how to prioritize and present his day?",
    "What did the most recent daily briefing and recent workflow run results report, decide, or leave open?",
]
def ask(q):
    r=subprocess.run(["python", "tools/run.py", "ask", q, "--top", "4"], cwd=v, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    return q,r.stdout[:5000]
answers={}
with ThreadPoolExecutor(max_workers=4) as pool:
    futures=[pool.submit(ask,q) for q in queries]
    for future in as_completed(futures):
        q,value=future.result(); answers[q]=value
for q in queries:
    parts.append(f"\n--- retrieval: {q} ---\n"+answers.get(q,""))
print("".join(parts)[:44000])
'''
        result = await self.exec(code, timeout=110)
        return result.get("stdout", "")[:44000]

    async def record(self, workflow: str, summary: str, details: list[str]) -> None:
        envelope = json.dumps({"summary": summary, "details": details}, ensure_ascii=False)
        code = f'''
import json, os, subprocess, tempfile
from pathlib import Path
v=Path(r"C:\\data\\DrShaye\\vault")
os.environ["DRSHAYE_AGENT"]="eli-dashboard"
payload=json.loads({json.dumps(envelope)})
marker=v/".run-active"
if marker.exists():
    raise SystemExit("Eli Agent run is active; dashboard write deferred")
s=subprocess.run(["python","tools/run.py","start","--workflow",{workflow!r}],cwd=v,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=60)
if s.returncode: raise SystemExit(s.stderr or s.stdout)
result={{"type":"dashboard","summary":payload["summary"],"workflow":{workflow!r},"mode":"approved_ui_action","results":payload["details"],"checks":[],"anomalies":[],"errors_hit":[],"new_errors":[],"learnings":[],"memory_candidates":[],"approvals_requested":[],"external_actions":[],"deferred":[]}}
p=v/"result-dashboard.json"; p.write_text(json.dumps(result,indent=2),encoding="utf-8")
f=subprocess.run(["python","tools/run.py","finish","--workflow",{workflow!r},"--json",str(p)],cwd=v,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=180)
try: p.unlink()
except OSError: pass
if f.returncode: raise SystemExit(f.stderr or f.stdout)
print("recorded")
'''
        await self.exec(code, timeout=240)


class ComposioMCPClient:
    READ_TOOLS = {"GMAIL_FETCH_EMAILS", "GOOGLECALENDAR_EVENTS_LIST"}
    WRITE_TOOLS = {"GMAIL_SEND_EMAIL", "GOOGLECALENDAR_CREATE_EVENT"}
    EMAIL_PATTERN = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")

    def __init__(self, settings: Settings):
        self.settings = settings
        self.key = settings.composio_consumer_api_key
        self.endpoint = "https://connect.composio.dev/mcp"

    @staticmethod
    def _decode_response(text: str) -> dict[str, Any]:
        if "data:" in text:
            data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
            text = data_lines[-1] if data_lines else "{}"
        return json.loads(text)

    async def _request(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        session_id: str | None = None,
        retry_transport: bool = False,
    ) -> tuple[dict[str, Any], str | None]:
        if not self.key:
            raise RuntimeError("Composio is not configured")
        headers = {
            "x-consumer-api-key": self.key,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        attempts = 3 if retry_transport else 1
        for attempt in range(attempts):
            try:
                response = await client.post(self.endpoint, headers=headers, json=payload)
                break
            except httpx.TransportError:
                if attempt + 1 == attempts:
                    raise
                await asyncio.sleep(0.4 * (attempt + 1))
        response.raise_for_status()
        return self._decode_response(response.text), response.headers.get("mcp-session-id") or session_id

    async def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            initialized, session_id = await self._request(
                client,
                {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"eli-command-center","version":"1.1"}}},
                retry_transport=True,
            )
            if "result" not in initialized:
                raise RuntimeError("Composio MCP initialization failed")
            response, _ = await self._request(
                client,
                {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":name,"arguments":arguments}},
                session_id,
            )
        if response.get("error"):
            raise RuntimeError("Composio MCP call failed")
        content = response.get("result", {}).get("content", [])
        text = next((block.get("text") for block in content if block.get("type") == "text"), None)
        if not text:
            raise RuntimeError("Composio returned no structured result")
        decoded = json.loads(text)
        if decoded.get("error") or not decoded.get("successful", True):
            raise RuntimeError("Composio tool execution failed")
        return decoded

    async def _multi_execute(self, tools: list[dict[str, Any]], step: str) -> list[dict[str, Any]]:
        result = await self._call(
            "COMPOSIO_MULTI_EXECUTE_TOOL",
            {
                "tools": tools,
                "sync_response_to_workbench": False,
                "thought": "Use exact, account-pinned contracts for the Eli dashboard.",
                "current_step": step,
                "current_step_metric": f"0/{len(tools)} tools",
            },
        )
        return result.get("data", {}).get("results", [])

    @staticmethod
    def _safe_signal(text: str) -> bool:
        blocked = r"\b(patient|gastro|clinic|hospital|colonoscopy|endoscopy|biopsy|pathology|diagnos(?:is|ed)|prescription|medical record|mrn)\b"
        return bool(text.strip()) and not contains_phi(text) and not re.search(blocked, text, re.I)

    async def personal_signals(self) -> str:
        """Return compact personal-account metadata; never mailbox bodies or event descriptions."""
        gmail_account = self.settings.composio_personal_gmail_account
        calendar_account = self.settings.composio_personal_calendar_account
        if not gmail_account or not calendar_account:
            raise RuntimeError("Personal Composio account IDs are not configured")
        now = datetime.now(timezone.utc)
        tools = [
            {
                "tool_slug": "GMAIL_FETCH_EMAILS",
                "arguments": {
                    "query": "in:inbox newer_than:7d -category:promotions -category:social",
                    "user_id": "me",
                    "verbose": False,
                    "ids_only": False,
                    "max_results": 25,
                    "include_payload": False,
                    "include_spam_trash": False,
                },
                "account": gmail_account,
            },
            {
                "tool_slug": "GOOGLECALENDAR_EVENTS_LIST",
                "arguments": {
                    "calendarId": "primary",
                    "timeMin": now.isoformat(),
                    "timeMax": (now + timedelta(days=7)).isoformat(),
                    "timeZone": self.settings.dashboard_timezone,
                    "singleEvents": True,
                    "orderBy": "startTime",
                    "maxResults": 25,
                    "showDeleted": False,
                },
                "account": calendar_account,
            },
        ]

        async def read_one(tool: dict[str, Any]) -> list[dict[str, Any]]:
            # Reads are idempotent, so one empty/transient response may be retried safely.
            result: list[dict[str, Any]] = []
            for _ in range(2):
                result = await self._multi_execute([tool], "FETCHING_PERSONAL_SIGNALS")
                response = result[0].get("response", {}) if result else {}
                if response.get("data"):
                    break
            return result

        batches = await asyncio.gather(*(read_one(tool) for tool in tools), return_exceptions=True)
        results = [item for batch in batches if isinstance(batch, list) for item in batch]
        lines: list[str] = []
        for item in results:
            response = item.get("response", {})
            if not response.get("successful"):
                continue
            data = response.get("data", {})
            if item.get("tool_slug") == "GMAIL_FETCH_EMAILS":
                messages = sorted(data.get("messages") or [], key=lambda m: m.get("messageTimestamp") or "", reverse=True)
                for message in messages[:20]:
                    subject = str(message.get("subject") or "").strip()[:180]
                    sender = str(message.get("sender") or "").strip()[:140]
                    signal = f"{subject} | from {sender}"
                    if self._safe_signal(signal):
                        lines.append(f"INBOX | {message.get('messageTimestamp') or 'time unknown'} | {signal}")
            elif item.get("tool_slug") == "GOOGLECALENDAR_EVENTS_LIST":
                for event in (data.get("items") or [])[:20]:
                    summary = str(event.get("summary") or "Busy").strip()[:180]
                    start = event.get("start") or {}
                    when = start.get("dateTime") or start.get("date") or "time unknown"
                    if self._safe_signal(summary):
                        lines.append(f"CALENDAR | {when} | {summary}")
        return "\n".join(lines[:30])

    @staticmethod
    def validate_write(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Narrow local schemas prevent arbitrary calls, aliases, HTML, and attachments."""
        if tool_name == "GMAIL_SEND_EMAIL":
            allowed = {"recipient_email", "extra_recipients", "subject", "body", "is_html", "user_id"}
            if set(arguments) - allowed:
                raise ValueError("Unsupported Gmail fields")
            recipient = arguments.get("recipient_email")
            if not isinstance(recipient, str) or not ComposioMCPClient.EMAIL_PATTERN.fullmatch(recipient):
                raise ValueError("A valid email recipient is required")
            subject = str(arguments.get("subject") or "").strip()
            body = str(arguments.get("body") or "").strip()
            if not subject or not body:
                raise ValueError("Email subject and body are required")
            if len(subject) > 200 or len(body) > 10000:
                raise ValueError("Email content exceeds the dashboard limits")
            extras = arguments.get("extra_recipients", [])
            if not isinstance(extras, list) or len(extras) > 20 or any(not isinstance(value, str) or not ComposioMCPClient.EMAIL_PATTERN.fullmatch(value) for value in extras):
                raise ValueError("Invalid additional recipient")
            clean = dict(arguments)
            clean["is_html"] = False
            clean["user_id"] = "me"
            return clean
        if tool_name == "GOOGLECALENDAR_CREATE_EVENT":
            allowed = {"summary", "description", "start_datetime", "event_duration_hour", "event_duration_minutes", "attendees", "timezone", "calendar_id", "create_meeting_room", "send_updates"}
            if set(arguments) - allowed:
                raise ValueError("Unsupported Calendar fields")
            summary = str(arguments.get("summary") or "").strip()
            start = str(arguments.get("start_datetime") or "").strip()
            if not summary or not start:
                raise ValueError("Calendar summary and start time are required")
            if len(summary) > 200 or len(str(arguments.get("description") or "")) > 4000:
                raise ValueError("Calendar content exceeds the dashboard limits")
            try:
                datetime.fromisoformat(start.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Calendar start time must be ISO 8601") from exc
            hours = arguments.get("event_duration_hour", 0)
            minutes = arguments.get("event_duration_minutes", 30)
            if not isinstance(hours, int) or not 0 <= hours <= 23 or not isinstance(minutes, int) or not 0 <= minutes <= 59 or hours + minutes == 0:
                raise ValueError("Calendar duration is invalid")
            attendees = arguments.get("attendees", [])
            if not isinstance(attendees, list) or len(attendees) > 50 or any(not isinstance(value, str) or not ComposioMCPClient.EMAIL_PATTERN.fullmatch(value) for value in attendees):
                raise ValueError("Calendar attendees must be email addresses")
            clean = dict(arguments)
            clean["calendar_id"] = "primary"
            clean["timezone"] = str(clean.get("timezone") or "America/Los_Angeles")
            clean["create_meeting_room"] = bool(clean.get("create_meeting_room", False))
            clean["send_updates"] = "all"
            return clean
        raise ValueError("Composio tool is not allowlisted")

    async def execute_allowlisted(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        clean = self.validate_write(tool_name, arguments)
        account = self.settings.composio_personal_gmail_account if tool_name.startswith("GMAIL_") else self.settings.composio_personal_calendar_account
        if not account:
            raise RuntimeError("Personal Composio account ID is not configured")
        results = await self._multi_execute([{"tool_slug": tool_name, "arguments": clean, "account": account}], "EXECUTING_APPROVED_ACTION")
        if len(results) != 1 or not results[0].get("response", {}).get("successful"):
            raise RuntimeError("Approved Composio action failed")
        response = results[0]["response"]
        data = response.get("data") or {}
        return {"successful": True, "tool": tool_name, "resource_id": data.get("id"), "resource_url": data.get("display_url") or data.get("htmlLink")}

    async def health(self) -> bool:
        async with httpx.AsyncClient(timeout=30) as client:
            result, _ = await self._request(client, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"eli-command-center","version":"1.1"}}}, retry_transport=True)
            return "result" in result


async def integration_health(settings: Settings) -> dict[str, bool]:
    orgo = EliAgentClient(settings)
    composio = ComposioMCPClient(settings)

    async def orgo_check() -> bool:
        try:
            result = await orgo.exec("import socket; print(socket.gethostname())", timeout=20)
            return "ORGOORG-PV7BNLD" in result.get("stdout", "")
        except Exception:
            return False

    async def composio_check() -> bool:
        try:
            return await composio.health()
        except Exception:
            return False

    eli_agent_ok, composio_ok = await asyncio.gather(orgo_check(), composio_check())
    return {"eli_agent": eli_agent_ok, "composio": composio_ok, "anthropic": bool(settings.anthropic_api_key)}
