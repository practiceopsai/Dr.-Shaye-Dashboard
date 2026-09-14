"""Read-only, stdlib-only production adapter. Also executed on the Orgo host.

Keep machine state out of the language-model context. Never read credentials,
conversation bodies, pending learning candidates, or raw document attachments.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import subprocess


def frontmatter(text):
    result = {}
    if text.startswith("---\n"):
        for line in text.split("---", 2)[1].splitlines():
            key, sep, value = line.partition(":")
            if sep:
                try:
                    result[key] = json.loads(value.strip())
                except (ValueError, TypeError):
                    result[key] = value.strip().strip('"')
    return result


def collect_snapshot(vault=Path(r"C:\data\DrShaye\vault"), home=None):
    now = datetime.now(timezone.utc)
    errors, sources, context = [], [], []

    def read_json(path):
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            errors.append(path.name + " unavailable")
            return {}

    if home is None:
        runtime = read_json(vault / "persona/_state/runtime.json")
        home = Path(runtime.get("hermes_home", r"C:\Users\Administrator\AppData\Local\hermes"))

    def source(rel, max_chars=3500, max_age_hours=None):
        path = vault / rel
        try:
            raw = path.read_text(encoding="utf-8-sig")
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError:
            return ""
        status = frontmatter(raw).get("status")
        if status in {"superseded", "disputed", "candidate", "rejected"}:
            return ""
        recent = max_age_hours is None or 0 <= (now - modified).total_seconds() <= max_age_hours * 3600
        sources.append({"path": rel, "modified_at": modified.isoformat(), "included": recent,
                        "revision": hashlib.sha256(raw.encode()).hexdigest()[:16]})
        if not recent:
            return ""
        if rel == "persona/CHARACTER.md":
            raw = raw.split("## Calibrated examples", 1)[0]
        context.append(f"\n--- {rel} | modified {modified.isoformat()} ---\n" + raw[:max_chars])
        return raw

    # Current approved policy and confirmed memory; no historical status timeline.
    for rel in ["persona/CHARACTER.md", "design/governance/approval-and-autonomy.md",
                "memory/preferences/eli-communication-standard-20260908.md",
                "memory/preferences/eli-automation-output-standard-20260909.md"]:
        source(rel)
    for folder in ["memory/preferences", "persona/user-model"]:
        for path in sorted((vault / folder).glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:12]:
            source(path.relative_to(vault).as_posix())
    for folder in ["briefings/morning", "daily-briefing/logs", "commitment-capture/logs"]:
        paths = sorted((vault / folder).glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if paths:
            source(paths[0].relative_to(vault).as_posix(), max_age_hours=36)

    stage_path = vault / "persona/STAGE.md"
    try:
        stage = frontmatter(stage_path.read_text(encoding="utf-8-sig"))
    except OSError:
        stage = {}
    autonomy = []
    for path in sorted((vault / "persona/autonomy").glob("*.md")):
        row = frontmatter(path.read_text(encoding="utf-8-sig"))
        autonomy.append({key: row.get(key) for key in ["category", "level", "clean_streak"]})
    health = read_json(home / "state/eli-health.json")
    gateway = read_json(home / "gateway_state.json")
    maintenance = read_json(vault / "persona/_state/maintenance-health.json")
    jobs = read_json(home / "cron/jobs.json")
    jobs = jobs.get("jobs", []) if isinstance(jobs, dict) else jobs
    retrieval = health.get("retrieval", {})
    summary = {
        "checked_at": now.isoformat(), "health_checked_at": health.get("checked_at"),
        "healthy": health.get("healthy") is True, "gateway": gateway.get("gateway_state", "unknown"),
        "gateway_checked_at": gateway.get("updated_at"),
        "platforms": {key: val.get("state", "unknown") for key, val in gateway.get("platforms", {}).items()},
        "memory": {key: retrieval.get(key) for key in ["status", "semantic", "files", "chunks", "checked_at"]},
        "persona": {"stage": stage.get("stage"), "character_review": stage.get("character_review", "unknown"),
                    "started_at": stage.get("started_at"), "status": maintenance.get("status", "unknown"),
                    "checked_at": maintenance.get("checked_at"), "autonomy": autonomy},
        "jobs": {"total": len(jobs), "enabled": sum(j.get("enabled") is True for j in jobs),
                 "failed": sum(j.get("enabled") is True and j.get("last_status") not in [None, "ok"] for j in jobs)},
        "alerts": [str(x) for x in health.get("alerts", [])], "read_errors": errors, "sources": sources,
    }
    # Stage and autonomy are observations, never new authority or permission.
    context.append("\n--- Current observed familiarity/autonomy; existing approval rules remain binding ---\n" +
                   json.dumps({"stage": stage.get("stage"), "autonomy": autonomy}))
    # Use Eli's installed retrieval implementation (including its exclusions).
    queries = [
        "Omid latest confirmed priority corrections preferences protected time priority escalation P0 P1 P2 P3 P4 P5",
        "Current open commitments deadlines waiting on active projects completed cancelled superseded",
        "Recent document email decisions obligations unresolved due dates",
    ]
    successes = 0
    for query in queries:
        try:
            result = subprocess.run(["python", "tools/run.py", "ask", query, "--top", "4"], cwd=vault,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
            if result.returncode:
                continue
            successes += 1
            # Every retrieval hit retains its source date. Old transient records
            # cannot quietly return as today's work through a lexical match.
            for block in re.split(r"(?=\[\d+\] )", result.stdout):
                match = re.match(r"\[\d+\] (.+?) ::", block)
                if not match:
                    continue
                rel = match.group(1).replace("\\", "/")
                path = (vault / rel).resolve()
                if not path.is_relative_to(vault.resolve()) or not path.is_file():
                    continue
                modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                transient = any(x in rel for x in ["/logs/", "briefings/", "source/interactions/"]) or rel == "CURRENT_STATUS.md"
                if transient and (now - modified).total_seconds() > 36 * 3600:
                    continue
                context.append(f"\n--- Retrieval evidence; source modified {modified.isoformat()} ---\n" + block[:2000])
        except (OSError, subprocess.TimeoutExpired):
            continue
    summary["retrieval_queries"] = {"succeeded": successes, "total": len(queries)}
    context.append(f"\nRAG queries succeeded: {successes}/{len(queries)}")
    return {"summary": summary, "context": "".join(context)[:70000]}
