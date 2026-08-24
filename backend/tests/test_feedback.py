from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture(autouse=True)
def feedback_state():
    main.app.dependency_overrides[main.require_auth] = lambda: None
    main._cache.clear()
    main._pending_feedback.clear()
    yield
    main.app.dependency_overrides.clear()
    main._cache.clear()
    main._pending_feedback.clear()


def test_priority_feedback_is_recorded_as_candidate_preference(monkeypatch):
    calls = []

    class RecordingClient:
        def __init__(self, settings):
            pass

        async def record(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(main, "EliAgentClient", RecordingClient)
    response = TestClient(main.app).post(
        "/api/feedback",
        json={"category": "priority_correction", "feedback": "Family commitments should rank above routine administration."},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "recorded"
    assert response.json()["next_brief_refresh"] is True
    assert calls[0][0][0] == "daily-briefing"
    assert calls[0][1]["memory_candidates"] == ["Candidate priority preference reported by Dr. Shaye: Family commitments should rank above routine administration."]


def test_item_feedback_writes_priority_context_to_agent_memory(monkeypatch):
    calls = []

    class RecordingClient:
        def __init__(self, settings):
            pass

        async def record(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(main, "EliAgentClient", RecordingClient)
    main._cache["dashboard"] = (
        datetime.now(timezone.utc),
        {
            "cards": [
                {
                    "id": "card-1",
                    "title": "Prepare the board agenda",
                    "priority": "P1",
                    "lane": "now",
                    "category": "Leadership",
                    "source": "morning brief",
                }
            ]
        },
    )

    response = TestClient(main.app).post(
        "/api/feedback",
        json={
            "category": "priority_correction",
            "item_id": "card-1",
            "disposition": "not_relevant",
            "feedback": "This should not be in today's brief.",
        },
    )

    assert response.status_code == 200
    candidate = calls[0][1]["memory_candidates"][0]
    assert "Disposition: not_relevant" in candidate
    assert "title: Prepare the board agenda" in candidate
    assert "priority: P1" in candidate
    assert "source: morning brief" in candidate


def test_dashboard_change_becomes_tracked_work_and_invalidates_cache(monkeypatch):
    calls = []

    class RecordingClient:
        def __init__(self, settings):
            pass

        async def record(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(main, "EliAgentClient", RecordingClient)
    main._cache["dashboard"] = (datetime.now(timezone.utc), {"cards": [{"id": "card-1"}]})
    response = TestClient(main.app).post(
        "/api/feedback",
        json={"category": "dashboard_change", "item_id": "card-1", "feedback": "Add a clearer owner indicator."},
    )

    assert response.status_code == 200
    assert response.json()["detail"] == "Dashboard improvement request recorded with Eli as tracked work."
    assert calls[0][0][0] == "commitment-capture"
    assert "dashboard" not in main._cache


def test_failed_writeback_is_queued_and_can_be_retried(monkeypatch):
    attempts = 0

    class RetryingClient:
        def __init__(self, settings):
            pass

        async def record(self, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("unavailable")

    monkeypatch.setattr(main, "EliAgentClient", RetryingClient)
    client = TestClient(main.app)
    queued = client.post(
        "/api/feedback",
        json={"category": "positive_reinforcement", "feedback": "This ordering was correct."},
    )

    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"
    assert queued.json()["retriable"] is True
    feedback_id = queued.json()["feedback_id"]
    retried = client.post(f"/api/feedback/{feedback_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "recorded"
    assert feedback_id not in main._pending_feedback


def test_feedback_rejects_phi_and_unknown_items(monkeypatch):
    class RecordingClient:
        def __init__(self, settings):
            pass

        async def record(self, *args, **kwargs):
            raise AssertionError("unsafe feedback must not be written")

    monkeypatch.setattr(main, "EliAgentClient", RecordingClient)
    client = TestClient(main.app)
    phi = client.post(
        "/api/feedback",
        json={"category": "priority_correction", "feedback": "Patient John Smith DOB: 1/2/1960"},
    )
    assert phi.status_code == 422

    main._cache["dashboard"] = (datetime.now(timezone.utc), {"cards": [{"id": "card-1"}]})
    unknown = client.post(
        "/api/feedback",
        json={"category": "priority_correction", "item_id": "card-2", "feedback": "This is not a priority."},
    )
    assert unknown.status_code == 422


def test_disposition_requires_an_item():
    response = TestClient(main.app).post(
        "/api/feedback",
        json={"category": "priority_correction", "disposition": "not_relevant", "feedback": "Remove this."},
    )
    assert response.status_code == 422
