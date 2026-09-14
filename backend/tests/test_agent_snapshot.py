from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json
import os
from app.agent_snapshot import collect_snapshot


def test_snapshot_excludes_historical_briefs_and_secret_state(tmp_path, monkeypatch):
    vault, home = tmp_path / "vault", tmp_path / "home"
    def write(root, rel, content):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
    old = write(vault, "briefings/morning/old.md", "OLD TASK SHOULD NOT APPEAR")
    os.utime(old, (1, 1))
    write(vault, "persona/CHARACTER.md", "Approved behavior\n## Calibrated examples\nPROPOSED EXAMPLE")
    write(vault, "memory/preferences/current.md", '---\nstatus: "confirmed"\n---\nConfirmed preference')
    write(vault, "memory/preferences/retired.md", '---\nstatus: "superseded"\n---\nRETIRED PREFERENCE')
    write(vault, "persona/STAGE.md", '---\nstage: 0\ncharacter_review: "approved"\n---\n')
    write(vault, "persona/_state/maintenance-health.json", '{"status":"healthy"}')
    write(home, "state/eli-health.json", '{"healthy":true,"retrieval":{"status":"healthy"},"secret":"HIDDEN"}')
    write(home, "gateway_state.json", '{"gateway_state":"running","platforms":{}}')
    write(home, "cron/jobs.json", '{"jobs":[]}')
    monkeypatch.setattr("app.agent_snapshot.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="[1] briefings/morning/old.md :: Old\nOLD TASK SHOULD NOT APPEAR"))
    snapshot = collect_snapshot(vault, home)
    text = json.dumps(snapshot)
    assert "Confirmed preference" in text
    for excluded in ["HIDDEN", "RETIRED PREFERENCE", "PROPOSED EXAMPLE", "OLD TASK SHOULD NOT APPEAR"]:
        assert excluded not in text
    assert any(row["path"] == "briefings/morning/old.md" and not row["included"] for row in snapshot["summary"]["sources"])
