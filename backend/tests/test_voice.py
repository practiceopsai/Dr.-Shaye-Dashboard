import asyncio

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture(autouse=True)
def voice_state():
    main.app.dependency_overrides[main.require_auth] = lambda: None
    main._cache.clear()
    main._pending_voice.clear()
    yield
    main.app.dependency_overrides.clear()
    main._cache.clear()
    main._pending_voice.clear()


def test_priority_voice_feedback_writes_agent_memory_and_rebuilds_brief(monkeypatch):
    calls = []

    class RecordingClient:
        def __init__(self, settings):
            pass

        async def record(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(main, "EliAgentClient", RecordingClient)
    main._cache["dashboard"] = (object(), object())

    response = TestClient(main.app).post(
        "/api/voice",
        json={"transcript": "Family time should be a higher priority in my daily brief."},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "recorded"
    assert body["intent"] == "priority_feedback"
    assert body["eli_agent_writeback"] is True
    assert body["next_brief_refresh"] is True
    assert "dashboard" not in main._cache
    assert calls[0][0][0] == "daily-briefing"
    assert "Family time should be a higher priority" in calls[0][1]["memory_candidates"][0]
    assert calls[0][1]["mode"] == "user_requested_unapproved"


def test_dashboard_voice_change_becomes_tracked_implementation_work(monkeypatch):
    calls = []

    class RecordingClient:
        def __init__(self, settings):
            pass

        async def record(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(main, "EliAgentClient", RecordingClient)
    response = TestClient(main.app).post(
        "/api/voice",
        json={"transcript": "Make the calendar widget larger on my dashboard."},
    )

    assert response.json()["intent"] == "dashboard_change"
    assert "tracked dashboard improvement" in response.json()["message"]
    assert calls[0][0][0] == "commitment-capture"
    assert calls[0][0][1] == "Dashboard improvement requested through Talk to Eli"


def test_action_voice_request_is_recorded_but_remains_approval_gated(monkeypatch):
    calls = []

    class RecordingClient:
        def __init__(self, settings):
            pass

        async def record(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(main, "EliAgentClient", RecordingClient)
    response = TestClient(main.app).post(
        "/api/voice",
        json={"transcript": "Draft a follow-up to the board chair."},
    )

    assert response.json()["intent"] == "action_request"
    assert "exact approval" in response.json()["message"]
    assert calls[0][0][1] == "Action requested through Talk to Eli"
    assert calls[0][1]["mode"] == "user_requested_unapproved"


def test_failed_voice_writeback_is_queued_and_retried(monkeypatch):
    attempts = 0

    class RetryingClient:
        def __init__(self, settings):
            pass

        async def record(self, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("busy")

    monkeypatch.setattr(main, "EliAgentClient", RetryingClient)
    response = TestClient(main.app).post(
        "/api/voice",
        json={"transcript": "Please prepare the agenda."},
    )

    command_id = response.json()["command_id"]
    assert response.json()["status"] == "queued"
    assert response.json()["retriable"] is True
    assert command_id in main._pending_voice

    asyncio.run(main._flush_pending_voice())
    assert command_id not in main._pending_voice


def test_voice_rejects_patient_identifiable_content(monkeypatch):
    class RecordingClient:
        def __init__(self, settings):
            pass

        async def record(self, *args, **kwargs):
            raise AssertionError("unsafe voice content must not be recorded")

    monkeypatch.setattr(main, "EliAgentClient", RecordingClient)
    response = TestClient(main.app).post(
        "/api/voice",
        json={"transcript": "Patient John Smith DOB: 1/2/1960 needs follow-up."},
    )

    assert response.status_code == 422
    assert not main._pending_voice
