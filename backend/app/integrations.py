import asyncio
import json
from typing import Any
import httpx
from .config import Settings


class OrgoHermesClient:
    """Durable bridge to Hermes: same production vault, retrieval, and run ledger."""

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
            raise RuntimeError(f"Hermes bridge exited {result.get('exit_code')}: {result.get('stderr', '')[-500:]}")
        return result

    async def context(self) -> str:
        code = r'''
from pathlib import Path
import subprocess
v=Path(r"C:\data\DrShaye\vault")
parts=[]
for rel in ["CURRENT_STATUS.md", "daily-briefing/PLAYBOOK.md", "design/governance/approval-and-autonomy.md"]:
    p=v/rel
    if p.exists(): parts.append(f"\n--- {rel} ---\n"+p.read_text(encoding="utf-8")[:7000])
for q in ["What commitments, deadlines, waiting-on items, and active projects matter now?", "What are Omid's current priority and protected-time rules?"]:
    r=subprocess.run(["python", "tools/run.py", "ask", q, "--top", "4"], cwd=v, capture_output=True, text=True, timeout=60)
    parts.append(f"\n--- retrieval: {q} ---\n"+r.stdout[:10000])
print("".join(parts))
'''
        result = await self.exec(code)
        return result.get("stdout", "")[-28000:]

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
    raise SystemExit("Hermes run is active; dashboard write deferred")
s=subprocess.run(["python","tools/run.py","start","--workflow",{workflow!r}],cwd=v,capture_output=True,text=True,timeout=60)
if s.returncode: raise SystemExit(s.stderr or s.stdout)
result={{"type":"dashboard","summary":payload["summary"],"workflow":{workflow!r},"mode":"approved_ui_action","results":payload["details"],"checks":[],"anomalies":[],"errors_hit":[],"new_errors":[],"learnings":[],"memory_candidates":[],"approvals_requested":[],"external_actions":[],"deferred":[]}}
p=v/"result-dashboard.json"; p.write_text(json.dumps(result,indent=2),encoding="utf-8")
f=subprocess.run(["python","tools/run.py","finish","--workflow",{workflow!r},"--json",str(p)],cwd=v,capture_output=True,text=True,timeout=180)
try: p.unlink()
except OSError: pass
if f.returncode: raise SystemExit(f.stderr or f.stdout)
print("recorded")
'''
        await self.exec(code, timeout=240)


class ComposioMCPClient:
    def __init__(self, settings: Settings):
        self.key = settings.composio_consumer_api_key
        self.endpoint = "https://connect.composio.dev/mcp"

    async def _request(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        if not self.key:
            raise RuntimeError("Composio is not configured")
        headers = {
            "x-consumer-api-key": self.key,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(self.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            session_id = response.headers.get("mcp-session-id")
            text = response.text
        if "data:" in text:
            data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
            text = data_lines[-1] if data_lines else "{}"
        return json.loads(text), session_id

    async def health(self) -> bool:
        payload = {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"eli-command-center","version":"1.0"}}}
        result, _ = await self._request(payload)
        return "result" in result


async def integration_health(settings: Settings) -> dict[str, bool]:
    orgo = OrgoHermesClient(settings)
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

    hermes_ok, composio_ok = await asyncio.gather(orgo_check(), composio_check())
    return {"hermes": hermes_ok, "composio": composio_ok, "anthropic": bool(settings.anthropic_api_key)}

