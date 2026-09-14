from datetime import datetime, timezone
import asyncio
from app import main
from app.models import DashboardPayload
from app.priorities import _recent, _rag_sync_ok


def test_previous_day_is_not_current_even_before_expiry():
    payload = DashboardPayload(generated_at="2026-09-14T06:58:00Z", expires_at="2026-09-14T07:03:00Z",
                               live=True, greeting="Hi", focus="", cards=[], integrations={})
    assert main._cache_current(payload, datetime(2026, 9, 14, 6, 59, tzinfo=timezone.utc))
    assert not main._cache_current(payload, datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc))


def test_health_requires_recent_timestamp_and_all_retrieval_queries():
    now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
    assert _recent("2026-09-14T11:55:00Z", now)
    assert not _recent("2026-09-13T11:55:00Z", now)
    assert not _recent(None, now)
    assert not _rag_sync_ok("RAG queries succeeded: 1/3")


def test_simultaneous_requests_share_one_refresh(monkeypatch):
    calls = []
    async def build(settings):
        from datetime import timedelta
        calls.append(1)
        await asyncio.sleep(.02)
        now = datetime.now(timezone.utc)
        return DashboardPayload(generated_at=now, expires_at=now+timedelta(minutes=5), live=True,
                                greeting="Hi", focus="", cards=[], integrations={})
    monkeypatch.setattr(main, "build_dashboard", build)
    async def check():
        main._cache.clear()
        main._refresh_lock = asyncio.Lock()
        a, b = await asyncio.gather(main._refresh_dashboard(True), main._refresh_dashboard(True))
        assert a is b
        main._cache.clear()
    asyncio.run(check())
    assert len(calls) == 1
